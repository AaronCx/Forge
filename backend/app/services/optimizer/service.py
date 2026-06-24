"""Self-optimization service — closes the loop between evals and agent configs.

Pipeline for a single optimization run:

1. Run a baseline eval of the agent against the suite.
2. Collect the failing cases. If there are none, short-circuit (nothing to
   optimize) — the agent already passes.
3. Generate N candidate system prompts from the failures (one model call via the
   injectable :class:`VariantGenerator`).
4. Run the eval suite against each candidate (concurrently), using the executor's
   ``prompt_override`` so the stored agent is never mutated.
5. Select the winner by suite-score delta over the baseline. If no candidate
   beats the baseline, record ``no_improvement`` and stop.
6. Create an approval request to promote the winner. The new prompt is NOT
   applied to the agent until that approval is approved — promotion happens in
   :meth:`apply_approved`.
7. Persist the lineage: parent prompt, every variant + its score, the winner and
   the delta.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db import get_db
from app.services.evals.approvals import approval_service
from app.services.evals.executor import EvalExecutor, eval_executor
from app.services.observability.prompt_versions import (
    PromptVersionService,
    prompt_version_service,
)
from app.services.optimizer.variant_generator import (
    PromptVariant,
    VariantGenerator,
    VariantRequest,
    default_variant_generator,
)

logger = logging.getLogger(__name__)

# How much a variant must beat the baseline by to be considered a winner.
MIN_IMPROVEMENT = 0.001


class OptimizerService:
    """Orchestrates eval-driven prompt optimization with an approval gate."""

    def __init__(
        self,
        *,
        executor: EvalExecutor | None = None,
        variant_generator: VariantGenerator | None = None,
        approvals: Any = None,
        prompt_versions: PromptVersionService | None = None,
    ) -> None:
        self._executor = executor or eval_executor
        self._variant_generator = variant_generator or default_variant_generator
        self._approvals = approvals or approval_service
        self._prompt_versions = prompt_versions or prompt_version_service

    async def optimize(
        self,
        *,
        user_id: str,
        agent_id: str,
        suite_id: str,
        n_variants: int = 3,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run one optimization attempt and return the lineage record."""
        agent = (
            get_db().table("agents")
            .select("*")
            .eq("id", agent_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        ).data
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        suite = (
            get_db().table("eval_suites")
            .select("*")
            .eq("id", suite_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        ).data
        if not suite:
            raise ValueError(f"Eval suite {suite_id} not found")
        if suite.get("target_type") != "agent" or suite.get("target_id") != agent_id:
            raise ValueError("Eval suite must target the agent being optimized")

        parent_prompt = agent.get("system_prompt", "")
        opt_run_id = str(uuid.uuid4())
        get_db().table("optimization_runs").insert({
            "id": opt_run_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "suite_id": suite_id,
            "status": "running",
            "parent_prompt": parent_prompt,
        }).execute()

        try:
            return await self._run(
                opt_run_id=opt_run_id,
                user_id=user_id,
                agent_id=agent_id,
                suite_id=suite_id,
                parent_prompt=parent_prompt,
                n_variants=n_variants,
                model=model,
            )
        except Exception as e:  # noqa: BLE001 - record failure, re-raise to caller
            logger.exception("Optimization run %s failed", opt_run_id)
            self._finalize(opt_run_id, {"status": "failed", "error": str(e)})
            raise

    async def _run(
        self,
        *,
        opt_run_id: str,
        user_id: str,
        agent_id: str,
        suite_id: str,
        parent_prompt: str,
        n_variants: int,
        model: str | None,
    ) -> dict[str, Any]:
        # 1. Baseline eval.
        baseline = await self._executor.run_suite(
            suite_id=suite_id,
            user_id=user_id,
            model=model,
            triggered_by="optimizer",
        )
        baseline_score = float(baseline.get("avg_score", 0.0) or 0.0)
        baseline_run_id = baseline.get("run_id")

        # 2. Collect failures. No failures → nothing to optimize.
        failures = self._collect_failures(baseline_run_id)
        if not failures:
            return self._finalize(opt_run_id, {
                "status": "no_failures",
                "baseline_run_id": baseline_run_id,
                "baseline_score": baseline_score,
                "summary": "Baseline eval has no failing cases; nothing to optimize.",
            })

        # 3. Generate candidate prompts (one model call).
        variants = await self._variant_generator(
            VariantRequest(
                current_prompt=parent_prompt,
                failures=failures,
                n=n_variants,
                model=model,
            )
        )
        variants = [v for v in variants if v.system_prompt.strip() and v.system_prompt != parent_prompt]
        if not variants:
            return self._finalize(opt_run_id, {
                "status": "no_improvement",
                "baseline_run_id": baseline_run_id,
                "baseline_score": baseline_score,
                "summary": "Variant generator produced no usable candidates.",
            })

        # 4. Score each candidate against the suite (concurrently).
        scored = await self._score_variants(
            opt_run_id=opt_run_id,
            variants=variants,
            suite_id=suite_id,
            user_id=user_id,
            model=model,
        )

        # 5. Select the winner by score delta.
        winner = max(scored, key=lambda v: v["score"])
        delta = winner["score"] - baseline_score
        if delta < MIN_IMPROVEMENT:
            return self._finalize(opt_run_id, {
                "status": "no_improvement",
                "baseline_run_id": baseline_run_id,
                "baseline_score": baseline_score,
                "winner_variant_id": winner["id"],
                "winner_score": winner["score"],
                "score_delta": delta,
                "summary": (
                    f"Best candidate scored {winner['score']:.3f} vs baseline "
                    f"{baseline_score:.3f} (+{delta:.3f}); below improvement threshold."
                ),
            })

        # Mark the winning variant row.
        get_db().table("optimization_variants").update(
            {"is_winner": True}
        ).eq("id", winner["id"]).execute()

        # 6. Gate the winner behind an approval — DO NOT auto-apply.
        suite_name = (
            get_db().table("eval_suites").select("name").eq("id", suite_id).single().execute()
        ).data
        suite_label = suite_name.get("name", suite_id) if suite_name else suite_id
        pct = delta * 100
        summary = (
            f"Optimized prompt beat baseline by +{pct:.1f}% on suite '{suite_label}' "
            f"({baseline_score:.3f} → {winner['score']:.3f})"
        )
        approval = await self._approvals.create_approval(
            user_id=user_id,
            blueprint_run_id=opt_run_id,
            node_id=f"optimizer:{agent_id}",
            context={
                "kind": "prompt_optimization",
                "optimization_run_id": opt_run_id,
                "agent_id": agent_id,
                "suite_id": suite_id,
                "variant_id": winner["id"],
                "baseline_score": baseline_score,
                "winner_score": winner["score"],
                "score_delta": delta,
                "system_prompt": winner["system_prompt"],
                "summary": summary,
            },
        )

        return self._finalize(opt_run_id, {
            "status": "awaiting_approval",
            "baseline_run_id": baseline_run_id,
            "baseline_score": baseline_score,
            "winner_variant_id": winner["id"],
            "winner_score": winner["score"],
            "score_delta": delta,
            "approval_id": approval.get("id"),
            "summary": summary,
        })

    async def _score_variants(
        self,
        *,
        opt_run_id: str,
        variants: list[PromptVariant],
        suite_id: str,
        user_id: str,
        model: str | None,
    ) -> list[dict[str, Any]]:
        """Run the suite against each variant concurrently; persist + return rows."""

        async def _score_one(index: int, variant: PromptVariant) -> dict[str, Any]:
            run = await self._executor.run_suite(
                suite_id=suite_id,
                user_id=user_id,
                model=model,
                triggered_by="optimizer",
                prompt_override=variant.system_prompt,
            )
            return {
                "index": index,
                "variant": variant,
                "eval_run_id": run.get("run_id"),
                "score": float(run.get("avg_score", 0.0) or 0.0),
                "pass_rate": float(run.get("pass_rate", 0.0) or 0.0),
            }

        results = await asyncio.gather(
            *(_score_one(i, v) for i, v in enumerate(variants))
        )

        rows: list[dict[str, Any]] = []
        for r in results:
            variant_id = str(uuid.uuid4())
            row = {
                "id": variant_id,
                "optimization_run_id": opt_run_id,
                "variant_index": r["index"],
                "system_prompt": r["variant"].system_prompt,
                "rationale": r["variant"].rationale,
                "eval_run_id": r["eval_run_id"],
                "score": r["score"],
                "pass_rate": r["pass_rate"],
                "is_winner": False,
            }
            get_db().table("optimization_variants").insert(row).execute()
            rows.append(row)
        return rows

    @staticmethod
    def _collect_failures(eval_run_id: str | None) -> list[dict[str, Any]]:
        """Pull failing cases for an eval run into a transcript-friendly shape."""
        if not eval_run_id:
            return []
        results = (
            get_db().table("eval_results")
            .select("*")
            .eq("run_id", eval_run_id)
            .execute()
        ).data or []

        failures: list[dict[str, Any]] = []
        for r in results:
            if r.get("passed"):
                continue
            case = (
                get_db().table("eval_cases").select("*").eq("id", r["case_id"]).single().execute()
            ).data or {}
            actual = r.get("actual_output") or {}
            details = r.get("grading_details") or {}
            failures.append({
                "case_id": r["case_id"],
                "input": case.get("input"),
                "expected": case.get("expected_output"),
                "actual": actual.get("text", actual) if isinstance(actual, dict) else actual,
                "reason": details.get("error") or details.get("reasoning") or details.get("method", ""),
            })
        return failures

    @staticmethod
    def _finalize(opt_run_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Write terminal fields onto the optimization run and return it."""
        update = dict(fields)
        update["completed_at"] = datetime.now(UTC).isoformat()
        get_db().table("optimization_runs").update(update).eq("id", opt_run_id).execute()
        get_run = (
            get_db().table("optimization_runs").select("*").eq("id", opt_run_id).single().execute()
        ).data
        return dict(get_run) if get_run else {"id": opt_run_id, **update}

    async def get_lineage(self, opt_run_id: str, user_id: str) -> dict[str, Any] | None:
        """Fetch an optimization run with its variants (the lineage record)."""
        run = (
            get_db().table("optimization_runs")
            .select("*")
            .eq("id", opt_run_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        ).data
        if not run:
            return None
        variants = (
            get_db().table("optimization_variants")
            .select("*")
            .eq("optimization_run_id", opt_run_id)
            .order("variant_index")
            .execute()
        ).data or []
        result = dict(run)
        result["variants"] = variants
        return result

    async def list_lineage(
        self, user_id: str, *, agent_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List optimization runs for a user, newest first."""
        query = (
            get_db().table("optimization_runs")
            .select("*")
            .eq("user_id", user_id)
        )
        if agent_id:
            query = query.eq("agent_id", agent_id)
        result = query.order("created_at", desc=True).limit(limit).execute()
        return result.data or []

    async def apply_approved(
        self, *, approval_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Promote a winner whose approval has been approved.

        Records a new prompt version (which also updates the agent's stored
        ``system_prompt``). Safe to call only after the approval is approved;
        returns ``None`` otherwise.
        """
        approval = await self._approvals.get_approval(approval_id)
        if not approval or approval.get("user_id") != user_id:
            return None
        if approval.get("status") != "approved":
            return None
        ctx = approval.get("context") or {}
        if ctx.get("kind") != "prompt_optimization":
            return None
        if ctx.get("applied"):
            # Already promoted — idempotent no-op (was creating duplicate versions).
            return None

        agent_id = ctx["agent_id"]
        new_prompt = ctx["system_prompt"]
        version = await self._prompt_versions.create_version(
            user_id=user_id,
            agent_id=agent_id,
            system_prompt=new_prompt,
            change_summary=ctx.get("summary", "Promoted by optimizer"),
        )
        # create_version deactivates prior versions but doesn't touch the agent
        # row; mirror prompt_version_service.rollback and update the live agent.
        get_db().table("agents").update(
            {"system_prompt": new_prompt}
        ).eq("id", agent_id).eq("user_id", user_id).execute()
        # Mark the approval consumed (status has a CHECK constraint, so flag it in
        # the context JSON) — the guard above makes re-applying a no-op instead of
        # duplicating the promoted prompt version.
        get_db().table("approvals").update(
            {"context": {**ctx, "applied": True}}
        ).eq("id", approval_id).eq("user_id", user_id).execute()
        return version


optimizer_service = OptimizerService()
