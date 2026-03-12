"""Eval framework API routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import supabase
from app.routers.auth import get_current_user
from app.services.evals.executor import eval_executor

router = APIRouter(tags=["evals"])


class EvalSuiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    target_type: str = Field(..., pattern="^(agent|blueprint)$")
    target_id: str


class EvalCaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    input: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    grading_method: str = "contains"
    grading_config: dict[str, Any] = Field(default_factory=dict)


class EvalRunRequest(BaseModel):
    model: str | None = None


# --- Suites ---


@router.post("/evals/suites")
async def create_suite(
    req: EvalSuiteCreate,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Create an eval suite."""
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user.id,
        "name": req.name,
        "description": req.description,
        "target_type": req.target_type,
        "target_id": req.target_id,
    }
    result = supabase.table("eval_suites").insert(row).execute()
    return result.data[0] if result.data else row


@router.get("/evals/suites")
async def list_suites(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List user's eval suites."""
    result = (
        supabase.table("eval_suites")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/evals/suites/{suite_id}")
async def get_suite(
    suite_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get an eval suite with its cases."""
    suite = (
        supabase.table("eval_suites")
        .select("*")
        .eq("id", suite_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    ).data
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    cases = (
        supabase.table("eval_cases")
        .select("*")
        .eq("suite_id", suite_id)
        .order("created_at")
        .execute()
    ).data or []

    suite["cases"] = cases
    return dict(suite)


@router.delete("/evals/suites/{suite_id}")
async def delete_suite(
    suite_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Delete an eval suite."""
    supabase.table("eval_suites").delete().eq("id", suite_id).eq("user_id", user.id).execute()
    return {"status": "deleted"}


# --- Cases ---


@router.post("/evals/suites/{suite_id}/cases")
async def create_case(
    suite_id: str,
    req: EvalCaseCreate,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Add a test case to a suite."""
    # Verify suite ownership
    suite = (
        supabase.table("eval_suites")
        .select("id")
        .eq("id", suite_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    ).data
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    row = {
        "id": str(uuid.uuid4()),
        "suite_id": suite_id,
        "name": req.name,
        "input": req.input,
        "expected_output": req.expected_output,
        "grading_method": req.grading_method,
        "grading_config": req.grading_config,
    }
    result = supabase.table("eval_cases").insert(row).execute()
    return result.data[0] if result.data else row


@router.delete("/evals/cases/{case_id}")
async def delete_case(
    case_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Delete a test case."""
    # Ownership check via suite
    case = (
        supabase.table("eval_cases").select("*, eval_suites!inner(user_id)").eq("id", case_id).single().execute()
    ).data
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    supabase.table("eval_cases").delete().eq("id", case_id).execute()
    return {"status": "deleted"}


# --- Runs ---


@router.post("/evals/suites/{suite_id}/run")
async def run_suite(
    suite_id: str,
    req: EvalRunRequest | None = None,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Execute an eval suite."""
    model = req.model if req else None
    result = await eval_executor.run_suite(
        suite_id=suite_id,
        user_id=user.id,
        model=model,
    )
    return result


@router.get("/evals/suites/{suite_id}/runs")
async def list_runs(
    suite_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List eval runs for a suite."""
    result = (
        supabase.table("eval_runs")
        .select("*")
        .eq("suite_id", suite_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/evals/runs/{run_id}")
async def get_run(
    run_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get detailed eval run results."""
    run = (
        supabase.table("eval_runs").select("*").eq("id", run_id).single().execute()
    ).data
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    results = (
        supabase.table("eval_results")
        .select("*")
        .eq("run_id", run_id)
        .order("created_at")
        .execute()
    ).data or []

    run["results"] = results
    return dict(run)


@router.get("/evals/runs/{run_id}/compare/{other_run_id}")
async def compare_runs(
    run_id: str,
    other_run_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Compare two eval runs to see regressions/improvements."""
    run_a = (supabase.table("eval_runs").select("*").eq("id", run_id).single().execute()).data
    run_b = (supabase.table("eval_runs").select("*").eq("id", other_run_id).single().execute()).data

    if not run_a or not run_b:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    results_a = (supabase.table("eval_results").select("*").eq("run_id", run_id).execute()).data or []
    results_b = (supabase.table("eval_results").select("*").eq("run_id", other_run_id).execute()).data or []

    # Index by case_id
    a_by_case = {r["case_id"]: r for r in results_a}
    b_by_case = {r["case_id"]: r for r in results_b}

    comparisons = []
    all_cases = set(a_by_case.keys()) | set(b_by_case.keys())

    for case_id in all_cases:
        a = a_by_case.get(case_id)
        b = b_by_case.get(case_id)
        comparison = {
            "case_id": case_id,
            "run_a_score": a["score"] if a else None,
            "run_b_score": b["score"] if b else None,
            "run_a_passed": a["passed"] if a else None,
            "run_b_passed": b["passed"] if b else None,
        }
        if a and b:
            score_diff = (b["score"] or 0) - (a["score"] or 0)
            comparison["score_diff"] = score_diff
            if a["passed"] and not b["passed"]:
                comparison["status"] = "regression"
            elif not a["passed"] and b["passed"]:
                comparison["status"] = "improvement"
            else:
                comparison["status"] = "unchanged"
        else:
            comparison["status"] = "new" if b else "removed"
            comparison["score_diff"] = 0

        comparisons.append(comparison)

    return {
        "run_a": {"id": run_id, "pass_rate": run_a.get("pass_rate"), "avg_score": run_a.get("avg_score")},
        "run_b": {"id": other_run_id, "pass_rate": run_b.get("pass_rate"), "avg_score": run_b.get("avg_score")},
        "comparisons": comparisons,
        "regressions": sum(1 for c in comparisons if c["status"] == "regression"),
        "improvements": sum(1 for c in comparisons if c["status"] == "improvement"),
    }
