"""Model comparison API — run the same prompt on multiple models side-by-side."""

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import supabase
from app.providers.registry import provider_registry
from app.routers.auth import get_current_user
from app.services.token_tracker import calculate_cost

logger = logging.getLogger(__name__)
router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    system_prompt: str = Field("You are a helpful assistant.", max_length=5000)
    models: list[str] = Field(..., min_length=2, max_length=5)
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(1024, ge=1, le=16384)


class CompareResultItem(BaseModel):
    model: str
    provider: str
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost: float
    error: str | None = None


class CompareResponse(BaseModel):
    id: str
    results: list[CompareResultItem]


@router.post("/compare", response_model=CompareResponse)
async def compare_models(
    req: CompareRequest,
    user=Depends(get_current_user),  # noqa: B008
):
    """Run the same prompt on multiple models and return results side-by-side."""
    # Create comparison record
    run_result = supabase.table("comparison_runs").insert({
        "user_id": user.id,
        "prompt": req.prompt,
        "models": req.models,
        "status": "running",
    }).execute()

    if not run_result.data:
        raise HTTPException(status_code=500, detail="Failed to create comparison run")

    run_id = run_result.data[0]["id"]

    messages = [
        {"role": "system", "content": req.system_prompt},
        {"role": "user", "content": req.prompt},
    ]

    async def run_model(model: str) -> CompareResultItem:
        start = time.monotonic()
        try:
            response = await provider_registry.complete(
                messages=messages,
                model=model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                fallback=False,
            )
            cost = calculate_cost(model, response.input_tokens, response.output_tokens)
            return CompareResultItem(
                model=response.model,
                provider=response.provider,
                content=response.content,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                cost=cost,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return CompareResultItem(
                model=model,
                provider="unknown",
                content="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=elapsed,
                cost=0,
                error=str(e),
            )

    results = await asyncio.gather(*[run_model(m) for m in req.models])
    result_list = list(results)

    # Store results
    supabase.table("comparison_runs").update({
        "status": "completed",
        "results": [r.model_dump() for r in result_list],
    }).eq("id", run_id).execute()

    return CompareResponse(id=run_id, results=result_list)


@router.get("/compare/{run_id}", response_model=CompareResponse)
async def get_comparison(
    run_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get a previous comparison run result."""
    result = (
        supabase.table("comparison_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    )
    if not result.data or result.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Comparison not found")

    return CompareResponse(
        id=result.data["id"],
        results=[CompareResultItem(**r) for r in (result.data.get("results") or [])],
    )
