import logging
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.mcp.tool_registry import tool_registry
from app.providers.registry import provider_registry
from app.services.tools.code_executor import code_executor
from app.services.tools.data_extractor import data_extractor
from app.services.tools.document_reader import document_reader
from app.services.tools.summarizer import summarizer
from app.services.tools.web_search import web_search

logger = logging.getLogger(__name__)

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

    def __init__(self, model: str | None = None, user_id: str | None = None):
        self.model = model or provider_registry.default_model
        self.user_id = user_id
        self._llm = None  # Created lazily

    async def _get_llm(self):
        """Get LLM instance, using user's provider config if available."""
        if self._llm:
            return self._llm

        api_key = os.getenv("OPENAI_API_KEY", "")

        # Try to get user's OpenAI key from provider_configs
        if self.user_id:
            try:
                from app.db import get_db

                result = (
                    get_db().table("provider_configs")
                    .select("api_key_encrypted")
                    .eq("user_id", self.user_id)
                    .eq("provider", "openai")
                    .eq("is_enabled", True)
                    .single()
                    .execute()
                )
                if result.data and result.data.get("api_key_encrypted"):
                    api_key = result.data["api_key_encrypted"]
            except Exception:
                pass

        if not api_key:
            return None

        self._llm = ChatOpenAI(  # type: ignore[call-arg, assignment]
            model=self.model,
            temperature=0,
            streaming=True,
            api_key=api_key,  # type: ignore[arg-type]
        )
        return self._llm

    def _resolve_tools(self, tool_names: list[str]):
        """Resolve tool name strings to actual LangChain tool instances.

        Returns a tuple of (langchain_tools, mcp_tool_names) where mcp_tool_names
        are tools that need to be called via MCP rather than locally.
        """
        lc_tools = []
        mcp_tools = []
        for name in tool_names:
            if name in TOOL_REGISTRY:
                lc_tools.append(TOOL_REGISTRY[name])
            elif not tool_registry.is_builtin(name):
                # Could be an MCP tool (format: "server_id:tool_name" or just name)
                mcp_tools.append(name)
        return lc_tools, mcp_tools

    async def execute(
        self,
        agent_config: dict,
        user_input: str,
        *,
        heartbeat_id: str | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """Execute an agent's workflow and yield streaming events."""
        from app.services.heartbeat import heartbeat_service
        from app.services.observability.trace_service import trace_service

        system_prompt = agent_config.get("system_prompt", "")
        tool_names = agent_config.get("tools", [])
        workflow_steps = agent_config.get("workflow_steps", [])
        tools, _mcp_tools = self._resolve_tools(tool_names)
        agent_id = agent_config.get("id")

        # Per-agent model override
        model = agent_config.get("model") or self.model

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
                result = await self._execute_step(system_prompt, step, user_input, accumulated_context, model=model)

            step_tokens = result.get("tokens", 0)
            total_tokens += step_tokens

            # Record trace span for this step
            if user_id:
                try:
                    await trace_service.record_span(
                        user_id=user_id,
                        span_type="agent_step",
                        span_name=f"Step {i}: {step[:100]}",
                        run_id=run_id,
                        agent_id=agent_id,
                        model=result.get("model") or model,
                        provider=result.get("provider"),
                        input_tokens=result.get("input_tokens", 0),
                        output_tokens=result.get("output_tokens", 0),
                        latency_ms=result.get("latency_ms", 0),
                        input_preview=user_input[:500],
                        output_preview=result["content"][:500],
                    )
                except Exception:
                    logger.warning("Failed to record trace span", exc_info=True)

                # Record per-step token usage so /api/costs/* aggregates can
                # see this run. Without this, cost-by-{agent,model,provider}
                # breakdowns return zero on every Ollama-only stack (the
                # blueprint engine writes here but the agent executor didn't
                # — surfaced by QA Findings #27 and #29).
                try:
                    from app.services.token_tracker import token_tracker

                    token_tracker.record(
                        run_id=run_id,
                        agent_id=agent_id,
                        user_id=user_id,
                        step_number=i,
                        model=result.get("model") or model or "unknown",
                        provider=result.get("provider") or "unknown",
                        input_tokens=result.get("input_tokens", 0),
                        output_tokens=result.get("output_tokens", 0),
                    )
                except Exception:
                    logger.warning("Failed to record token usage", exc_info=True)

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
        llm = await self._get_llm()
        if not llm:
            # No OpenAI key — fall back to non-tool step via provider registry
            return await self._execute_step(system_prompt, step, user_input, context, model=self.model)

        prompt = ChatPromptTemplate.from_messages([
            ("system", f"{system_prompt}\n\nCurrent task: {step}"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_openai_tools_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)

        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"

        result = await executor.ainvoke({"input": full_input})

        return {
            "content": result.get("output", ""),
            "tokens": 0,
        }

    async def _execute_step(
        self, system_prompt: str, step: str, user_input: str, context: str, *, model: str | None = None
    ) -> dict:
        """Execute a single workflow step via the provider registry."""
        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"

        messages = [
            {"role": "system", "content": f"{system_prompt}\n\nCurrent task: {step}"},
            {"role": "user", "content": full_input},
        ]

        # Use user's provider registry if available
        if self.user_id:
            from app.providers.registry import create_user_registry

            registry = await create_user_registry(self.user_id)
        else:
            registry = provider_registry

        response = await registry.complete(
            messages=messages,
            model=model,
            temperature=0,
        )

        return {
            "content": response.content,
            "tokens": response.input_tokens + response.output_tokens,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "model": response.model,
            "provider": response.provider,
        }
