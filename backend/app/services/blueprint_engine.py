"""Blueprint execution engine — runs a DAG of deterministic and agent nodes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.database import supabase
from app.services.blueprint_nodes.agent_nodes import AGENT_EXECUTORS
from app.services.blueprint_nodes.context_assembly import assemble_context
from app.services.blueprint_nodes.deterministic import DETERMINISTIC_EXECUTORS
from app.services.blueprint_nodes.registry import NODE_REGISTRY
from app.services.computer_use.agent_nodes import CU_AGENT_EXECUTORS
from app.services.computer_use.drive.nodes import DRIVE_EXECUTORS
from app.services.computer_use.steer.nodes import STEER_EXECUTORS

# Merge computer use executors into the dispatch tables
_ALL_DETERMINISTIC = {**DETERMINISTIC_EXECUTORS, **STEER_EXECUTORS, **DRIVE_EXECUTORS}
_ALL_AGENT = {**AGENT_EXECUTORS, **CU_AGENT_EXECUTORS}
from app.services.token_tracker import calculate_cost, token_tracker

logger = logging.getLogger(__name__)


def _topological_sort(nodes: list[dict]) -> list[list[int]]:
    """
    Topologically sort nodes into execution layers.
    Returns a list of layers, where each layer contains node indices
    that can run concurrently.
    """
    n = len(nodes)
    node_map = {node["id"]: i for i, node in enumerate(nodes)}

    # Build adjacency / in-degree
    in_degree = [0] * n
    dependents: dict[int, list[int]] = {i: [] for i in range(n)}

    for i, node in enumerate(nodes):
        deps = node.get("dependencies", [])
        for dep_id in deps:
            dep_idx = node_map.get(dep_id)
            if dep_idx is not None:
                in_degree[i] += 1
                dependents[dep_idx].append(i)

    # BFS layering
    layers: list[list[int]] = []
    ready = [i for i in range(n) if in_degree[i] == 0]

    while ready:
        layers.append(ready[:])
        next_ready = []
        for idx in ready:
            for dep_idx in dependents[idx]:
                in_degree[dep_idx] -= 1
                if in_degree[dep_idx] == 0:
                    next_ready.append(dep_idx)
        ready = next_ready

    # Check for cycles
    total_sorted = sum(len(layer) for layer in layers)
    if total_sorted < n:
        raise ValueError("Blueprint DAG contains a cycle")

    return layers


class BlueprintEngine:
    """Executes a blueprint DAG: deterministic nodes run as code, agent nodes call LLMs."""

    async def execute(
        self,
        *,
        blueprint: dict,
        input_payload: dict[str, Any],
        user_id: str,
        run_id: str,
    ) -> AsyncIterator[dict]:
        """Execute a full blueprint and yield progress events."""
        nodes: list[dict] = blueprint.get("nodes", [])
        context_config = blueprint.get("context_config", {})
        retry_policy = blueprint.get("retry_policy", {"max_retries": 2})
        max_retries = retry_policy.get("max_retries", 2)
        total_nodes = len(nodes)

        if not nodes:
            yield {"type": "error", "data": "Blueprint has no nodes"}
            return

        # Sort into execution layers
        try:
            layers = _topological_sort(nodes)
        except ValueError as e:
            yield {"type": "error", "data": str(e)}
            return

        yield {"type": "status", "data": f"Executing blueprint: {total_nodes} nodes in {len(layers)} layers"}

        # Track per-node outputs and execution trace
        node_outputs: dict[str, dict[str, Any]] = {}
        execution_trace: list[dict] = []
        total_input_tokens = 0
        total_output_tokens = 0

        # Inject input_payload as a virtual "input" node output
        node_outputs["_input"] = input_payload

        for layer_idx, layer in enumerate(layers):
            yield {
                "type": "layer_start",
                "data": {"layer": layer_idx, "nodes": [nodes[i]["id"] for i in layer]},
            }

            # Execute nodes in this layer concurrently
            async def execute_node(idx: int) -> tuple[int, dict[str, Any]]:
                node = nodes[idx]
                node_id = node["id"]
                node_type_key = node.get("type", "")
                node_config = node.get("config", {})
                node_label = node.get("label", node_type_key)

                # Determine if deterministic or agent
                node_type = NODE_REGISTRY.get(node_type_key)
                if not node_type:
                    raise ValueError(f"Unknown node type: {node_type_key}")

                # Gather inputs from dependencies
                dep_ids = node.get("dependencies", [])
                upstream = {}
                for dep_id in dep_ids:
                    if dep_id in node_outputs:
                        upstream.update(node_outputs[dep_id])
                # Also include global input
                if "_input" in node_outputs:
                    for k, v in node_outputs["_input"].items():
                        if k not in upstream:
                            upstream[k] = v

                start_time = time.time()
                output: dict[str, Any] = {}
                node_tokens = {"input_tokens": 0, "output_tokens": 0}

                if node_type.node_class == "deterministic":
                    executor = _ALL_DETERMINISTIC.get(node_type_key)
                    if not executor:
                        raise ValueError(f"No executor for deterministic node: {node_type_key}")

                    output = await executor(node_config, upstream)

                elif node_type.node_class == "agent":
                    executor = _ALL_AGENT.get(node_type_key)
                    if not executor:
                        raise ValueError(f"No executor for agent node: {node_type_key}")

                    # Assemble context from upstream deterministic outputs
                    assembled = assemble_context(
                        {dep_id: node_outputs[dep_id] for dep_id in dep_ids if dep_id in node_outputs},
                        context_config=context_config,
                        objective=node_config.get("system_prompt", ""),
                    )
                    if assembled:
                        upstream["text"] = assembled

                    # Execute with retry
                    last_error = None
                    for attempt in range(max_retries + 1):
                        try:
                            output = await executor(node_config, upstream)
                            node_tokens["input_tokens"] = output.get("input_tokens", 0)
                            node_tokens["output_tokens"] = output.get("output_tokens", 0)
                            last_error = None
                            break
                        except Exception as e:
                            last_error = e
                            if attempt < max_retries:
                                logger.warning(
                                    "Agent node %s attempt %d failed: %s",
                                    node_id, attempt + 1, e,
                                )
                                continue

                    if last_error:
                        raise last_error

                duration_ms = int((time.time() - start_time) * 1000)

                trace_entry = {
                    "node_id": node_id,
                    "node_type": node_type_key,
                    "label": node_label,
                    "node_class": node_type.node_class,
                    "duration_ms": duration_ms,
                    "input_tokens": node_tokens["input_tokens"],
                    "output_tokens": node_tokens["output_tokens"],
                    "output_preview": str(output.get("text", output.get("formatted", "")))[:500],
                }

                return idx, {
                    "output": output,
                    "trace": trace_entry,
                    "tokens": node_tokens,
                }

            # Run all nodes in this layer concurrently
            tasks = [execute_node(idx) for idx in layer]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, BaseException):
                    node_idx = layer[results.index(result)]
                    node_id = nodes[node_idx]["id"]
                    yield {
                        "type": "node_error",
                        "data": {"node_id": node_id, "error": str(result)},
                    }
                    # Update run as failed
                    supabase.table("blueprint_runs").update({
                        "status": "failed",
                        "execution_trace": execution_trace,
                    }).eq("id", run_id).execute()
                    return

                idx, data = result
                node = nodes[idx]
                node_id = node["id"]

                node_outputs[node_id] = data["output"]
                execution_trace.append(data["trace"])
                total_input_tokens += data["tokens"]["input_tokens"]
                total_output_tokens += data["tokens"]["output_tokens"]

                yield {
                    "type": "node_done",
                    "data": {
                        "node_id": node_id,
                        "label": node.get("label", node.get("type", "")),
                        "node_class": data["trace"]["node_class"],
                        "duration_ms": data["trace"]["duration_ms"],
                        "tokens": data["tokens"]["input_tokens"] + data["tokens"]["output_tokens"],
                        "preview": data["trace"]["output_preview"][:200],
                    },
                }

            yield {"type": "layer_done", "data": {"layer": layer_idx}}

        # Get final output from the last node
        last_node_id = nodes[-1]["id"]
        final_output = node_outputs.get(last_node_id, {})

        # Format final result
        result_text = (
            final_output.get("formatted")
            or final_output.get("text")
            or final_output.get("summary")
            or final_output.get("code")
            or json.dumps(final_output)
        )

        # Record token usage
        if total_input_tokens > 0 or total_output_tokens > 0:
            try:
                token_tracker.record(
                    run_id=run_id,
                    agent_id=blueprint.get("id", ""),
                    user_id=user_id,
                    step_number=0,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )
            except Exception:
                logger.warning("Failed to record token usage for blueprint run %s", run_id)

        # Update run
        supabase.table("blueprint_runs").update({
            "status": "completed",
            "output": {"result": result_text, "total_tokens": total_input_tokens + total_output_tokens},
            "execution_trace": execution_trace,
            "completed_at": "now()",
        }).eq("id", run_id).execute()

        yield {
            "type": "result",
            "data": result_text,
            "tokens": total_input_tokens + total_output_tokens,
            "cost": calculate_cost(
                "", total_input_tokens, total_output_tokens
            ),
            "trace": execution_trace,
        }


blueprint_engine = BlueprintEngine()
