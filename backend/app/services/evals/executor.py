"""Eval execution service — runs eval suites against agents/blueprints."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.database import supabase
from app.providers.registry import provider_registry
from app.services.evals.grading import GRADING_METHODS

logger = logging.getLogger(__name__)


class EvalExecutor:
    """Executes eval suites: runs each test case, grades results, records stats."""

    async def run_suite(
        self,
        *,
        suite_id: str,
        user_id: str,
        model: str | None = None,
        triggered_by: str = "manual",
    ) -> dict[str, Any]:
        """Execute an eval suite and return the run summary."""
        # Get suite
        suite = (
            supabase.table("eval_suites")
            .select("*")
            .eq("id", suite_id)
            .single()
            .execute()
        ).data
        if not suite:
            raise ValueError(f"Eval suite {suite_id} not found")

        # Get cases
        cases = (
            supabase.table("eval_cases")
            .select("*")
            .eq("suite_id", suite_id)
            .order("created_at")
            .execute()
        ).data or []

        if not cases:
            raise ValueError("Eval suite has no test cases")

        # Create run record
        run_id = str(uuid.uuid4())
        supabase.table("eval_runs").insert({
            "id": run_id,
            "suite_id": suite_id,
            "triggered_by": triggered_by,
            "model_used": model or provider_registry.default_model,
            "status": "running",
            "total_cases": len(cases),
            "started_at": datetime.now(UTC).isoformat(),
        }).execute()

        # Execute each case
        results = []
        passed_count = 0
        total_score = 0.0

        for case in cases:
            try:
                result = await self._execute_case(
                    case=case,
                    suite=suite,
                    run_id=run_id,
                    model=model,
                )
                results.append(result)
                if result.get("passed"):
                    passed_count += 1
                total_score += result.get("score", 0.0)
            except Exception as e:
                logger.warning("Eval case %s failed: %s", case["id"], e)
                # Record failure
                result = {
                    "case_id": case["id"],
                    "passed": False,
                    "score": 0.0,
                    "actual_output": {"error": str(e)},
                    "grading_details": {"error": str(e)},
                    "latency_ms": 0,
                    "tokens_used": 0,
                }
                results.append(result)
                self._save_result(run_id, result)

        # Update run with results
        total = len(cases)
        pass_rate = passed_count / total if total > 0 else 0.0
        avg_score = total_score / total if total > 0 else 0.0

        supabase.table("eval_runs").update({
            "status": "completed",
            "pass_rate": pass_rate,
            "avg_score": avg_score,
            "passed_cases": passed_count,
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", run_id).execute()

        return {
            "run_id": run_id,
            "suite_id": suite_id,
            "total_cases": total,
            "passed_cases": passed_count,
            "pass_rate": pass_rate,
            "avg_score": avg_score,
            "status": "completed",
        }

    async def _execute_case(
        self,
        *,
        case: dict[str, Any],
        suite: dict[str, Any],
        run_id: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Execute a single eval case."""
        input_data = case.get("input", {})
        expected = case.get("expected_output", {})
        grading_method = case.get("grading_method", "contains")
        grading_config = case.get("grading_config", {})

        # Run the agent/blueprint to get actual output
        start = time.time()
        actual_output = await self._get_output(
            target_type=suite["target_type"],
            target_id=suite["target_id"],
            input_data=input_data,
            model=model,
        )
        latency_ms = int((time.time() - start) * 1000)

        actual_text = actual_output.get("text", json.dumps(actual_output))
        expected_text = expected.get("text", json.dumps(expected)) if expected else ""
        tokens = actual_output.get("tokens", 0)

        # Grade
        if grading_method == "human":
            grading_result = {
                "passed": False,
                "score": 0.0,
                "method": "human",
                "status": "pending_review",
            }
        elif grading_method in GRADING_METHODS:
            grader = GRADING_METHODS[grading_method]
            if asyncio.iscoroutinefunction(grader) or inspect.iscoroutinefunction(grader):
                grading_result = await grader(actual_text, expected_text, grading_config)
            else:
                grading_result = grader(actual_text, expected_text, grading_config)  # type: ignore[assignment]
        else:
            grading_result = {"passed": False, "score": 0.0, "error": f"Unknown grading method: {grading_method}"}

        result = {
            "case_id": case["id"],
            "actual_output": actual_output,
            "score": grading_result.get("score", 0.0),
            "passed": grading_result.get("passed", False),
            "grading_details": grading_result,
            "latency_ms": latency_ms,
            "tokens_used": tokens,
        }

        self._save_result(run_id, result)
        return result

    async def _get_output(
        self,
        *,
        target_type: str,
        target_id: str,
        input_data: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run an agent or blueprint and capture output."""
        input_text = input_data.get("text", input_data.get("input_text", json.dumps(input_data)))

        if target_type == "agent":
            # Simple LLM call using the agent's system prompt
            agent = (
                supabase.table("agents")
                .select("*")
                .eq("id", target_id)
                .single()
                .execute()
            ).data

            if not agent:
                raise ValueError(f"Agent {target_id} not found")

            resolved_model = model or agent.get("model") or None
            response = await provider_registry.complete(
                messages=[
                    {"role": "system", "content": agent.get("system_prompt", "")},
                    {"role": "user", "content": input_text},
                ],
                model=resolved_model,
                temperature=0,
            )
            return {
                "text": response.content,
                "tokens": response.input_tokens + response.output_tokens,
                "model": response.model,
            }

        elif target_type == "blueprint":
            # For blueprints, run the engine — simplified for eval purposes
            response = await provider_registry.complete(
                messages=[
                    {"role": "system", "content": "Process the following input."},
                    {"role": "user", "content": input_text},
                ],
                model=model,
                temperature=0,
            )
            return {
                "text": response.content,
                "tokens": response.input_tokens + response.output_tokens,
            }

        raise ValueError(f"Unknown target type: {target_type}")

    def _save_result(self, run_id: str, result: dict[str, Any]) -> None:
        """Save a single eval result to the database."""
        supabase.table("eval_results").insert({
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "case_id": result["case_id"],
            "actual_output": result.get("actual_output"),
            "score": result.get("score", 0.0),
            "passed": result.get("passed", False),
            "grading_details": result.get("grading_details", {}),
            "latency_ms": result.get("latency_ms", 0),
            "tokens_used": result.get("tokens_used", 0),
        }).execute()


eval_executor = EvalExecutor()
