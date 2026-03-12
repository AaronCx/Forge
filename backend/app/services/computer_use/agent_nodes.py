"""Computer use agent node executors — LLM-powered reasoning for GUI/terminal actions."""

from __future__ import annotations

import json
from typing import Any

from app.providers.registry import provider_registry


async def _cu_llm_call(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = "",
    json_mode: bool = False,
) -> dict[str, Any]:
    """Make an LLM call for computer use reasoning."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = await provider_registry.complete(
        messages=messages,
        model=model or None,
        temperature=0,
        max_tokens=4096,
    )
    return {
        "content": response.content,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_tokens": response.input_tokens + response.output_tokens,
        "model": response.model,
        "provider": response.provider,
    }


async def execute_cu_planner(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Plan the next sequence of GUI/terminal actions given an objective and screen state."""
    objective = config.get("objective") or inputs.get("objective", "")
    screen_text = inputs.get("text", "")
    elements = inputs.get("elements", [])
    screenshot = inputs.get("screenshot_base64", "")

    system_prompt = (
        "You are a computer use planning agent. Given an objective and the current screen state, "
        "plan the next sequence of GUI and terminal actions to achieve the objective.\n\n"
        "Available action types:\n"
        "- steer_see: Take a screenshot (target: app name or 'screen')\n"
        "- steer_ocr: Read text from screen (target: app name or 'screen')\n"
        "- steer_click: Click at coordinates (x, y) or on element text\n"
        "- steer_type: Type text into focused app\n"
        "- steer_hotkey: Send keyboard shortcut (e.g. 'cmd+s')\n"
        "- steer_scroll: Scroll up/down/left/right\n"
        "- steer_focus: Focus an app by name\n"
        "- steer_find: Find a UI element by text\n"
        "- steer_wait: Wait for text to appear on screen\n"
        "- drive_run: Execute a terminal command\n"
        "- drive_session: Create/list/kill tmux sessions\n"
        "- drive_logs: Capture terminal output\n\n"
        "Return a JSON array of steps, each with 'action' (node type) and 'args' (dict of arguments).\n"
        "Example: [{\"action\": \"steer_focus\", \"args\": {\"app\": \"Safari\"}}, "
        "{\"action\": \"steer_click\", \"args\": {\"element_text\": \"Search\"}}]"
    )

    user_prompt = f"Objective: {objective}\n\n"
    if screen_text:
        user_prompt += f"Current screen text:\n{screen_text[:4000]}\n\n"
    if elements:
        user_prompt += f"Detected UI elements: {json.dumps(elements[:50])}\n\n"
    user_prompt += "Plan the next actions:"

    result = await _cu_llm_call(system_prompt, user_prompt, model=config.get("model", ""), json_mode=True)

    try:
        plan = json.loads(result["content"])
        if not isinstance(plan, list):
            plan = [plan]
    except json.JSONDecodeError:
        plan = [{"action": "unknown", "reasoning": result["content"]}]

    return {
        "text": json.dumps(plan, indent=2),
        "plan": plan,
        "step_count": len(plan),
        "tokens": result["total_tokens"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "provider": result["provider"],
    }


async def execute_cu_analyzer(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Analyze a screenshot or OCR results to extract relevant information."""
    screen_text = inputs.get("text", "")
    elements = inputs.get("elements", [])
    focus = config.get("focus", "")

    system_prompt = (
        "You are a screen analysis agent. Analyze the current screen state and extract "
        "relevant information. Identify: what app is active, what content is displayed, "
        "any error messages, form fields, buttons, and actionable elements.\n"
        "Return a JSON object with: 'app', 'state', 'content', 'errors', 'actions_available', 'summary'."
    )

    user_prompt = ""
    if focus:
        user_prompt = f"Focus on: {focus}\n\n"
    if screen_text:
        user_prompt += f"Screen text:\n{screen_text[:6000]}\n\n"
    if elements:
        user_prompt += f"UI elements: {json.dumps(elements[:50])}\n\n"
    user_prompt += "Analyze this screen state:"

    result = await _cu_llm_call(system_prompt, user_prompt, model=config.get("model", ""), json_mode=True)

    try:
        analysis = json.loads(result["content"])
    except json.JSONDecodeError:
        analysis = {"summary": result["content"]}

    return {
        "text": analysis.get("summary", result["content"]),
        "analysis": analysis,
        "tokens": result["total_tokens"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "provider": result["provider"],
    }


async def execute_cu_verifier(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Verify if an objective was achieved by reviewing the current screen state."""
    objective = config.get("objective") or inputs.get("objective", "")
    screen_text = inputs.get("text", "")
    expected = config.get("expected", "")

    system_prompt = (
        "You are a verification agent. Review the current screen state and determine "
        "if the objective was achieved successfully.\n"
        "Return a JSON object with: 'success' (boolean), 'confidence' (0-1), "
        "'explanation' (what you see), 'retry_actions' (array of suggested actions if failed)."
    )

    user_prompt = f"Objective: {objective}\n\n"
    if expected:
        user_prompt += f"Expected result: {expected}\n\n"
    if screen_text:
        user_prompt += f"Current screen text:\n{screen_text[:6000]}\n\n"
    user_prompt += "Was the objective achieved?"

    result = await _cu_llm_call(system_prompt, user_prompt, model=config.get("model", ""), json_mode=True)

    try:
        verification = json.loads(result["content"])
    except json.JSONDecodeError:
        verification = {"success": False, "explanation": result["content"]}

    return {
        "text": verification.get("explanation", result["content"]),
        "success": verification.get("success", False),
        "confidence": verification.get("confidence", 0),
        "retry_actions": verification.get("retry_actions", []),
        "tokens": result["total_tokens"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "provider": result["provider"],
    }


async def execute_cu_error_handler(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Analyze an error and the current screen state to decide how to recover."""
    error = config.get("error") or inputs.get("error", "")
    screen_text = inputs.get("text", "")
    original_action = config.get("original_action") or inputs.get("original_action", "")

    system_prompt = (
        "You are an error recovery agent for computer use automation. An action failed. "
        "Analyze the error and current screen state, then suggest recovery actions.\n"
        "Common recovery patterns:\n"
        "- Dialog appeared: dismiss it and retry\n"
        "- Element not found: try OCR to find it, or scroll\n"
        "- App not responding: wait and retry, or force quit and reopen\n"
        "- Permission denied: check if approval is needed\n\n"
        "Return a JSON object with: 'diagnosis', 'recoverable' (boolean), "
        "'recovery_actions' (array of action steps), 'should_abort' (boolean)."
    )

    user_prompt = f"Error: {error}\n\n"
    if original_action:
        user_prompt += f"Original action that failed: {original_action}\n\n"
    if screen_text:
        user_prompt += f"Current screen text:\n{screen_text[:4000]}\n\n"
    user_prompt += "Diagnose and suggest recovery:"

    result = await _cu_llm_call(system_prompt, user_prompt, model=config.get("model", ""), json_mode=True)

    try:
        recovery = json.loads(result["content"])
    except json.JSONDecodeError:
        recovery = {"diagnosis": result["content"], "recoverable": False}

    return {
        "text": recovery.get("diagnosis", result["content"]),
        "recoverable": recovery.get("recoverable", False),
        "recovery_actions": recovery.get("recovery_actions", []),
        "should_abort": recovery.get("should_abort", False),
        "tokens": result["total_tokens"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "model": result["model"],
        "provider": result["provider"],
    }


# Executor dispatch table
CU_AGENT_EXECUTORS = {
    "cu_planner": execute_cu_planner,
    "cu_analyzer": execute_cu_analyzer,
    "cu_verifier": execute_cu_verifier,
    "cu_error_handler": execute_cu_error_handler,
}
