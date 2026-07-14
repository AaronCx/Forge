# forge-kernel

A provider-neutral, dependency-light agent kernel, extracted from
[Forge](https://github.com/AaronCx/Forge). Pure Python, **zero runtime
dependencies** — no FastAPI, no LangChain.

- **Types** — `KMessage`, typed content blocks (`TextBlock`, `ImageBlock`,
  `ToolUseBlock`, `ToolResultBlock`, `ThinkingBlock`), `TurnResult`,
  `StreamEvent`, `ToolSpec`.
- **Model cards** — data-driven model knowledge (`load_model_cards`,
  `get_model_card`) from a bundled `models.json`.
- **Converters** — lossless `from_openai_messages` / `to_openai_messages`.
- **Loop** — `run_agent_turn(messages, tools, model, *, registry, plane, ctx)`:
  streams a turn, executes any requested tools through your plane, appends the
  results, and repeats until the model stops or a `Budget` is hit.

Bring your own `registry` (any object with `async def stream(...)` yielding
kernel `StreamEvent`s) and `plane` (any object with `async def execute(...)`).

```bash
pip install forge-kernel
python demo/standalone_agent.py
```

See `demo/standalone_agent.py` for a ~30-line standalone agent.
