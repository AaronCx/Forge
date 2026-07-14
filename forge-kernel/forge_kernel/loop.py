"""The Forge-native agent loop (harness-plan.md Phase 4).

Provider-neutral, tool-plane-driven, streamed. One kernel turn runs on the
registry; if it stops to call tools, the plane executes them under policy, the
results are appended, and the loop continues until the model stops or a budget
is hit. Cancellation propagates through the async generator.

The loop is observer-agnostic: pass a ``recorder`` to capture time-travel events
and a ``budget`` to bound tokens/wall-clock. It yields the provider's
``StreamEvent``s plus a ``ToolExecuted`` marker per tool call so callers can
render rich progress; the terminal ``TurnDone`` of each turn carries the full
``TurnResult``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from forge_kernel.types import (
    KMessage,
    StreamEvent,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    TurnDone,
    TurnResult,
)


@dataclass
class Budget:
    """Bounds a run's tokens and wall-clock. ``None`` limits are unbounded."""

    max_tokens: int | None = None
    max_seconds: float | None = None
    _started: float = field(default_factory=time.monotonic)
    _tokens: int = 0

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        self._tokens += input_tokens + output_tokens

    @property
    def tokens_spent(self) -> int:
        return self._tokens

    def exceeded(self) -> bool:
        if self.max_tokens is not None and self._tokens >= self.max_tokens:
            return True
        if self.max_seconds is not None:
            return (time.monotonic() - self._started) >= self.max_seconds
        return False


@dataclass
class ToolExecuted:
    """A completed tool call — yielded by the loop after the plane runs it."""

    tool_use: ToolUseBlock
    result: ToolResultBlock
    kind: str = field(default="tool_executed", init=False)


LoopEvent = StreamEvent | ToolExecuted


async def run_agent_turn(
    messages: list[KMessage],
    tools: list[ToolSpec] | None,
    model: str | None,
    *,
    registry: object,
    plane: object,
    ctx: object,
    recorder: object | None = None,
    budget: Budget | None = None,
    max_iterations: int = 12,
    step: int = 0,
) -> AsyncIterator[LoopEvent]:
    """Run the kernel agent loop, mutating ``messages`` in place as it goes.

    Yields the provider stream events plus a ``ToolExecuted`` per tool call.
    Stops when a turn does not request tools, ``max_iterations`` is reached, or
    the ``budget`` is exhausted.
    """
    for _ in range(max_iterations):
        turn: TurnResult | None = None
        async for ev in registry.stream(messages, model, tools=tools):  # type: ignore[attr-defined]
            if isinstance(ev, TurnDone):
                turn = ev.turn
            yield ev

        if turn is None:
            return

        if recorder is not None:
            recorder.model_turn(step, turn)  # type: ignore[attr-defined]
        if budget is not None:
            budget.add_usage(turn.usage.input_tokens, turn.usage.output_tokens)

        if turn.stop_reason != "tool_use":
            return

        # Record the assistant turn, then execute each requested tool.
        messages.append(KMessage(role="assistant", blocks=list(turn.blocks)))
        results: list[ToolResultBlock] = []
        for tool_use in turn.tool_calls:
            result = await plane.execute(tool_use, ctx)  # type: ignore[attr-defined]
            if recorder is not None:
                recorder.tool_call_kernel(step, tool_use, result)  # type: ignore[attr-defined]
            results.append(result)
            yield ToolExecuted(tool_use=tool_use, result=result)
        messages.append(KMessage(role="tool", blocks=list(results)))

        if budget is not None and budget.exceeded():
            return
