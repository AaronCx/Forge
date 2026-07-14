"""A standalone agent in ~30 lines, embedding forge-kernel (no Forge backend).

Run: `python demo/standalone_agent.py`. Swap FakeRegistry for a real provider
(any object with `async def stream(messages, model, *, tools)` yielding kernel
StreamEvents) and FakePlane for your tools to make it real.
"""

import asyncio

from forge_kernel import KMessage, TextBlock, ToolResultBlock, run_agent_turn
from forge_kernel.types import TurnDone, TurnResult, Usage


class FakeRegistry:
    async def stream(self, messages, model, *, tools=None):
        reply = f"You said: {messages[-1].blocks[0].text}"
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock(reply)], stop_reason="end",
            usage=Usage(input_tokens=5, output_tokens=7),
            model=model or "demo", provider="demo",
        ))


class FakePlane:
    async def execute(self, tool_use, ctx):
        return ToolResultBlock(tool_use_id=tool_use.id, output="ok")


async def main() -> None:
    messages = [KMessage(role="user", blocks=[TextBlock("hello kernel")])]
    async for event in run_agent_turn(
        messages, tools=None, model="demo",
        registry=FakeRegistry(), plane=FakePlane(), ctx=None,
    ):
        if isinstance(event, TurnDone):
            print(event.turn.text)


if __name__ == "__main__":
    asyncio.run(main())
