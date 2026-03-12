import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.services.tools.code_executor import code_executor
from app.services.tools.data_extractor import data_extractor
from app.services.tools.document_reader import document_reader
from app.services.tools.summarizer import summarizer
from app.services.tools.web_search import web_search

load_dotenv()

TOOL_REGISTRY = {
    "web_search": web_search,
    "document_reader": document_reader,
    "code_executor": code_executor,
    "data_extractor": data_extractor,
    "summarizer": summarizer,
}


class AgentRunner:
    """Executes agent workflows step-by-step using LangChain with tool integration."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            streaming=True,
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    def _resolve_tools(self, tool_names: list[str]):
        """Resolve tool name strings to actual tool instances."""
        return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]

    async def execute(
        self, agent_config: dict, user_input: str, *, heartbeat_id: str | None = None
    ) -> AsyncIterator[dict]:
        """Execute an agent's workflow and yield streaming events."""
        from app.services.heartbeat import heartbeat_service

        system_prompt = agent_config.get("system_prompt", "")
        tool_names = agent_config.get("tools", [])
        workflow_steps = agent_config.get("workflow_steps", [])
        tools = self._resolve_tools(tool_names)

        if not workflow_steps:
            workflow_steps = ["Process the user's input according to your instructions."]

        if heartbeat_id:
            heartbeat_service.update(
                heartbeat_id, state="running", current_step=0
            )

        yield {"type": "step", "content": f"Starting agent: {agent_config.get('name', 'Unnamed')}", "tokens": 0}

        accumulated_context = ""
        total_tokens = 0

        for i, step in enumerate(workflow_steps, 1):
            yield {"type": "step", "content": f"Step {i}: {step}", "tokens": 0}

            if heartbeat_id:
                heartbeat_service.update(
                    heartbeat_id, state="running", current_step=i
                )

            if tools:
                result = await self._execute_with_tools(system_prompt, step, user_input, accumulated_context, tools)
            else:
                result = await self._execute_step(system_prompt, step, user_input, accumulated_context)

            step_tokens = result.get("tokens", 0)
            total_tokens += step_tokens

            if heartbeat_id:
                heartbeat_service.update(
                    heartbeat_id,
                    tokens_used=total_tokens,
                    output_preview=result["content"][:500],
                )

            accumulated_context += f"\n\n--- Step {i} result ---\n{result['content']}"
            yield {"type": "token", "content": result["content"], "tokens": step_tokens}
            yield {"type": "step", "content": f"Step {i} completed", "tokens": 0}

        if heartbeat_id:
            heartbeat_service.complete(heartbeat_id, tokens_used=total_tokens)

    async def _execute_with_tools(
        self, system_prompt: str, step: str, user_input: str, context: str, tools: list
    ) -> dict:
        """Execute a step using LangChain agent with tools."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"{system_prompt}\n\nCurrent task: {step}"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_openai_tools_agent(self.llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)

        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"

        result = await executor.ainvoke({"input": full_input})

        return {
            "content": result.get("output", ""),
            "tokens": 0,
        }

    async def _execute_step(self, system_prompt: str, step: str, user_input: str, context: str) -> dict:
        """Execute a single workflow step using the OpenAI API directly."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"

        messages = [
            {"role": "system", "content": f"{system_prompt}\n\nCurrent task: {step}"},
            {"role": "user", "content": full_input},
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
