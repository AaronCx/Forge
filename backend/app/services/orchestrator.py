"""Orchestrator service for multi-agent task decomposition and coordination."""

import asyncio
import json
from collections.abc import AsyncIterator

from app.database import supabase
from app.providers.registry import provider_registry
from app.services.agent_executor import AgentRunner
from app.services.messaging import messaging_service

AGENT_ROLES = {
    "coordinator": "Decomposes high-level objectives into sub-tasks",
    "supervisor": "Manages and monitors worker agents",
    "worker": "Executes implementation tasks",
    "scout": "Research and read-only exploration",
    "reviewer": "Validates and reviews results",
}


class Orchestrator:
    """Decomposes objectives into sub-tasks and coordinates worker agents."""

    def __init__(self):
        self.runner = AgentRunner()

    async def decompose(self, objective: str, available_tools: list[str]) -> list[dict]:
        """Use LLM to decompose an objective into sub-tasks with dependencies."""
        tools_str = ", ".join(available_tools) if available_tools else "none"

        response = await provider_registry.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You decompose objectives into concrete sub-tasks. "
                        "Return a JSON array of tasks. Each task has:\n"
                        '- "description": what to do\n'
                        '- "role": one of coordinator, supervisor, worker, scout, reviewer\n'
                        '- "dependencies": array of task indices (0-based) that must complete first\n'
                        '- "tools": array of tool names to use\n'
                        f"Available tools: {tools_str}\n"
                        "Keep tasks focused and independent where possible. "
                        "Return ONLY valid JSON array, no other text."
                    ),
                },
                {"role": "user", "content": objective},
            ],
            temperature=0,
        )

        content = response.content or "[]"
        try:
            parsed = json.loads(content)
            tasks = parsed.get("tasks", parsed) if isinstance(parsed, dict) else parsed
            if not isinstance(tasks, list):
                tasks = [tasks]
            return list(tasks)
        except json.JSONDecodeError:
            return [{"description": objective, "role": "worker", "dependencies": [], "tools": available_tools}]

    async def run(
        self,
        *,
        objective: str,
        user_id: str,
        tools: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        """Orchestrate a full objective: decompose -> dispatch -> aggregate."""
        available_tools = tools or []

        # Create task group
        group_result = supabase.table("task_groups").insert({
            "user_id": user_id,
            "objective": objective,
            "status": "planning",
        }).execute()
        group_id = group_result.data[0]["id"]

        yield {"type": "status", "data": "Decomposing objective into sub-tasks..."}

        # Decompose
        try:
            tasks = await self.decompose(objective, available_tools)
        except Exception as e:
            yield {"type": "error", "data": f"Failed to decompose: {e}"}
            supabase.table("task_groups").update({"status": "failed"}).eq("id", group_id).execute()
            return

        # Validate dependency indices
        num_tasks = len(tasks)
        for i, task in enumerate(tasks):
            deps = task.get("dependencies", [])
            valid_deps = [d for d in deps if isinstance(d, int) and 0 <= d < num_tasks and d != i]
            task["dependencies"] = valid_deps

        # Store plan
        supabase.table("task_groups").update({
            "plan": tasks,
            "status": "running",
        }).eq("id", group_id).execute()

        yield {"type": "plan", "data": tasks}

        # Create task group members
        members = []
        for i, task in enumerate(tasks):
            member_result = supabase.table("task_group_members").insert({
                "group_id": group_id,
                "task_description": task.get("description", ""),
                "dependencies": task.get("dependencies", []),
                "status": "pending",
                "sort_order": i,
            }).execute()
            members.append(member_result.data[0])

        # Execute tasks respecting dependencies
        results: dict[int, str] = {}
        completed: set[int] = set()

        while len(completed) < len(tasks):
            # Find tasks ready to run (all dependencies completed)
            ready = []
            for i, task in enumerate(tasks):
                if i in completed:
                    continue
                deps = task.get("dependencies", [])
                if all(d in completed for d in deps):
                    ready.append(i)

            if not ready:
                yield {"type": "error", "data": "Deadlock: no tasks can proceed"}
                break

            # Run ready tasks concurrently
            async def run_task(idx: int) -> tuple[int, str]:
                task = tasks[idx]
                member = members[idx]

                # Update status
                supabase.table("task_group_members").update(
                    {"status": "running"}
                ).eq("id", member["id"]).execute()

                # Send start message
                messaging_service.broadcast(
                    group_id=group_id,
                    sender_index=idx,
                    content=f"Starting: {task.get('description', '')}",
                    message_type="info",
                )

                # Build context from dependencies and their messages
                dep_context = ""
                for dep_idx in task.get("dependencies", []):
                    if dep_idx in results:
                        dep_context += f"\n--- Result from task {dep_idx + 1} ---\n{results[dep_idx]}\n"
                        # Send handoff message from dependency to this task
                        messaging_service.send(
                            group_id=group_id,
                            sender_index=dep_idx,
                            receiver_index=idx,
                            message_type="handoff",
                            content=results[dep_idx][:500],
                        )

                # Build agent config
                config = {
                    "name": f"Task {idx + 1}: {task.get('role', 'worker')}",
                    "system_prompt": (
                        f"You are a {task.get('role', 'worker')} agent. "
                        f"Complete this task: {task.get('description', '')}"
                    ),
                    "tools": task.get("tools", []),
                    "workflow_steps": [task.get("description", "Execute the task")],
                }

                # Execute
                full_output = ""
                async for event in self.runner.execute(config, dep_context or "Begin task."):
                    if event.get("type") == "token":
                        full_output += event.get("content", "")

                # Send completion message
                messaging_service.broadcast(
                    group_id=group_id,
                    sender_index=idx,
                    content=f"Completed: {full_output[:200]}",
                    message_type="response",
                )

                # Update member
                supabase.table("task_group_members").update({
                    "status": "completed",
                    "result": full_output[:2000],
                }).eq("id", member["id"]).execute()

                return idx, full_output

            # Run all ready tasks concurrently
            coros = [run_task(i) for i in ready]
            for task_idx in ready:
                yield {
                    "type": "task_start",
                    "data": {"index": task_idx, "description": tasks[task_idx].get("description", "")},
                }

            task_results = await asyncio.gather(*coros, return_exceptions=True)

            for result in task_results:
                if isinstance(result, BaseException):
                    yield {"type": "error", "data": str(result)}
                    continue
                idx, output = result  # type: ignore[misc]
                results[idx] = output
                completed.add(idx)
                yield {
                    "type": "task_done",
                    "data": {"index": idx, "preview": output[:200]},
                }

        # Final synthesis
        yield {"type": "status", "data": "Synthesizing results..."}

        all_results = "\n\n".join(
            f"Task {i + 1} ({tasks[i].get('description', '')}):\n{results.get(i, 'No result')}"
            for i in range(len(tasks))
        )

        try:
            synthesis = await provider_registry.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "Synthesize the results of multiple sub-tasks into a coherent final answer.",
                    },
                    {
                        "role": "user",
                        "content": f"Objective: {objective}\n\nTask Results:\n{all_results}",
                    },
                ],
                temperature=0,
            )
            final = synthesis.content or ""
        except Exception as e:
            final = f"Synthesis failed: {e}\n\nRaw results:\n{all_results}"

        # Update group
        supabase.table("task_groups").update({
            "status": "completed",
            "result": final,
        }).eq("id", group_id).execute()

        yield {"type": "result", "data": final, "group_id": group_id}


orchestrator = Orchestrator()
