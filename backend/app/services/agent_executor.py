import os
from typing import AsyncIterator
from dotenv import load_dotenv

load_dotenv()


class AgentRunner:
    """Executes agent workflows step-by-step.

    Full LangChain integration is implemented in the tools module.
    This class orchestrates the workflow steps defined in the agent config.
    """

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    async def execute(self, agent_config: dict, user_input: str) -> AsyncIterator[dict]:
        """Execute an agent's workflow and yield streaming events."""
        system_prompt = agent_config.get("system_prompt", "")
        tools = agent_config.get("tools", [])
        workflow_steps = agent_config.get("workflow_steps", [])

        # If no explicit workflow steps, run as a single-step agent
        if not workflow_steps:
            workflow_steps = ["Process the user's input according to your instructions."]

        yield {"type": "step", "content": f"Starting agent: {agent_config.get('name', 'Unnamed')}", "tokens": 0}

        for i, step in enumerate(workflow_steps, 1):
            yield {"type": "step", "content": f"Step {i}: {step}", "tokens": 0}

            # Execute step with LLM
            result = await self._execute_step(system_prompt, step, user_input, tools)

            yield {"type": "token", "content": result["content"], "tokens": result.get("tokens", 0)}
            yield {"type": "step", "content": f"Step {i} completed", "tokens": 0}

    async def _execute_step(self, system_prompt: str, step: str, user_input: str, tools: list[str]) -> dict:
        """Execute a single workflow step using the OpenAI API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)

        messages = [
            {"role": "system", "content": f"{system_prompt}\n\nCurrent task: {step}"},
            {"role": "user", "content": user_input},
        ]

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
        )

        choice = response.choices[0]
        return {
            "content": choice.message.content or "",
            "tokens": response.usage.total_tokens if response.usage else 0,
        }
