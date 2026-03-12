"""Node type registry — defines all available node types for blueprints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeType:
    """Definition of a blueprint node type."""

    key: str
    display_name: str
    category: str  # context, transform, validate, agent, output
    node_class: str  # "deterministic" or "agent"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""


# --- Deterministic node types ---

DETERMINISTIC_NODES: dict[str, NodeType] = {
    "fetch_url": NodeType(
        key="fetch_url",
        display_name="Fetch URL",
        category="context",
        node_class="deterministic",
        description="Fetches a URL and returns the text content.",
        input_schema={"url": {"type": "string", "required": True}},
        output_schema={"text": {"type": "string"}},
    ),
    "fetch_document": NodeType(
        key="fetch_document",
        display_name="Fetch Document",
        category="context",
        node_class="deterministic",
        description="Extracts text from an uploaded PDF, DOCX, or TXT file.",
        input_schema={"file_url": {"type": "string", "required": True}},
        output_schema={"text": {"type": "string"}},
    ),
    "run_linter": NodeType(
        key="run_linter",
        display_name="Run Linter",
        category="validate",
        node_class="deterministic",
        description="Runs a linter/formatter on code and returns errors or clean output.",
        input_schema={
            "code": {"type": "string", "required": True},
            "language": {"type": "string", "default": "python"},
        },
        output_schema={"result": {"type": "string"}, "has_errors": {"type": "boolean"}},
    ),
    "json_validator": NodeType(
        key="json_validator",
        display_name="JSON Validator",
        category="validate",
        node_class="deterministic",
        description="Validates output against a JSON schema.",
        input_schema={
            "data": {"type": "string", "required": True},
            "schema": {"type": "object", "required": True},
        },
        output_schema={"valid": {"type": "boolean"}, "errors": {"type": "array"}},
    ),
    "text_splitter": NodeType(
        key="text_splitter",
        display_name="Text Splitter",
        category="transform",
        node_class="deterministic",
        description="Splits long text into chunks with configurable size and overlap.",
        input_schema={
            "text": {"type": "string", "required": True},
            "chunk_size": {"type": "integer", "default": 2000},
            "overlap": {"type": "integer", "default": 200},
        },
        output_schema={"chunks": {"type": "array"}},
    ),
    "template_renderer": NodeType(
        key="template_renderer",
        display_name="Template Renderer",
        category="transform",
        node_class="deterministic",
        description="Renders a prompt template with variables from previous node outputs.",
        input_schema={
            "template": {"type": "string", "required": True},
            "variables": {"type": "object", "default": {}},
        },
        output_schema={"rendered": {"type": "string"}},
    ),
    "webhook": NodeType(
        key="webhook",
        display_name="Webhook",
        category="output",
        node_class="deterministic",
        description="Sends an HTTP POST to a URL with the current state.",
        input_schema={
            "url": {"type": "string", "required": True},
            "payload": {"type": "object", "default": {}},
        },
        output_schema={"status_code": {"type": "integer"}, "response": {"type": "string"}},
    ),
    "output_formatter": NodeType(
        key="output_formatter",
        display_name="Output Formatter",
        category="output",
        node_class="deterministic",
        description="Formats the final result as JSON, markdown, or plain text.",
        input_schema={
            "data": {"type": "string", "required": True},
            "format": {"type": "string", "default": "markdown", "enum": ["json", "markdown", "plain"]},
        },
        output_schema={"formatted": {"type": "string"}},
    ),
    "approval_gate": NodeType(
        key="approval_gate",
        display_name="Approval Gate",
        category="validate",
        node_class="deterministic",
        description="Pauses execution for human review. Requires approval before continuing.",
        input_schema={
            "message": {"type": "string", "default": "Please review and approve to continue."},
            "notify": {"type": "string", "default": "dashboard", "enum": ["dashboard", "pushover", "webhook"]},
        },
        output_schema={"approved": {"type": "boolean"}, "feedback": {"type": "string"}},
    ),
    "knowledge_retrieval": NodeType(
        key="knowledge_retrieval",
        display_name="Knowledge Retrieval",
        category="context",
        node_class="deterministic",
        description="Retrieves relevant chunks from a knowledge collection using semantic search.",
        input_schema={
            "collection_id": {"type": "string", "required": True},
            "query": {"type": "string", "required": True},
            "top_k": {"type": "integer", "default": 5},
        },
        output_schema={"chunks": {"type": "array"}, "context": {"type": "string"}},
    ),
}

# --- Agent node types ---

AGENT_NODES: dict[str, NodeType] = {
    "llm_generate": NodeType(
        key="llm_generate",
        display_name="LLM Generate",
        category="agent",
        node_class="agent",
        description="General-purpose LLM call with system and user prompt.",
        input_schema={
            "system_prompt": {"type": "string", "required": True},
            "user_prompt": {"type": "string", "default": ""},
        },
        output_schema={"text": {"type": "string"}, "tokens": {"type": "integer"}},
    ),
    "llm_summarize": NodeType(
        key="llm_summarize",
        display_name="LLM Summarize",
        category="agent",
        node_class="agent",
        description="Summarize input text with configurable length.",
        input_schema={
            "text": {"type": "string", "required": True},
            "max_length": {"type": "string", "default": "medium", "enum": ["short", "medium", "long"]},
        },
        output_schema={"summary": {"type": "string"}, "tokens": {"type": "integer"}},
    ),
    "llm_extract": NodeType(
        key="llm_extract",
        display_name="LLM Extract",
        category="agent",
        node_class="agent",
        description="Extract structured data from text into a defined schema.",
        input_schema={
            "text": {"type": "string", "required": True},
            "extraction_schema": {"type": "object", "default": {}},
        },
        output_schema={"extracted": {"type": "object"}, "tokens": {"type": "integer"}},
    ),
    "llm_review": NodeType(
        key="llm_review",
        display_name="LLM Review",
        category="agent",
        node_class="agent",
        description="Review code or text and return feedback with severity ratings.",
        input_schema={
            "content": {"type": "string", "required": True},
            "review_type": {"type": "string", "default": "code", "enum": ["code", "text", "security"]},
        },
        output_schema={"feedback": {"type": "array"}, "tokens": {"type": "integer"}},
    ),
    "llm_implement": NodeType(
        key="llm_implement",
        display_name="LLM Implement",
        category="agent",
        node_class="agent",
        description="Given a task description and context, generate code.",
        input_schema={
            "task": {"type": "string", "required": True},
            "language": {"type": "string", "default": "python"},
            "context": {"type": "string", "default": ""},
        },
        output_schema={"code": {"type": "string"}, "tokens": {"type": "integer"}},
    ),
}

# --- Steer node types (GUI automation) ---

STEER_NODES: dict[str, NodeType] = {
    "steer_see": NodeType(
        key="steer_see",
        display_name="Screenshot",
        category="computer_use_gui",
        node_class="deterministic",
        description="Capture a screenshot of a specific app, window, or the full screen.",
        input_schema={
            "target": {"type": "string", "default": "screen", "description": "App name, window title, or 'screen'"},
            "region": {"type": "string", "default": "", "description": "Optional region coordinates"},
        },
        output_schema={"screenshot_path": {"type": "string"}, "screenshot_base64": {"type": "string"}},
    ),
    "steer_ocr": NodeType(
        key="steer_ocr",
        display_name="OCR Read",
        category="computer_use_gui",
        node_class="deterministic",
        description="Extract all text from the screen or a specific app window using OCR.",
        input_schema={
            "target": {"type": "string", "default": "screen"},
            "store": {"type": "boolean", "default": False, "description": "Store elements for addressing"},
        },
        output_schema={"text": {"type": "string"}, "elements": {"type": "array"}, "element_count": {"type": "integer"}},
    ),
    "steer_click": NodeType(
        key="steer_click",
        display_name="Click",
        category="computer_use_gui",
        node_class="deterministic",
        description="Click at specific coordinates or on a detected text element.",
        input_schema={
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"},
            "element_text": {"type": "string", "description": "Text of element to click (alternative to x,y)"},
        },
        output_schema={"screenshot_after": {"type": "string"}, "success": {"type": "boolean"}},
    ),
    "steer_type": NodeType(
        key="steer_type",
        display_name="Type Text",
        category="computer_use_gui",
        node_class="deterministic",
        description="Type text into the currently focused application.",
        input_schema={
            "text": {"type": "string", "required": True},
            "target": {"type": "string", "default": "", "description": "App to focus first"},
        },
        output_schema={"success": {"type": "boolean"}},
    ),
    "steer_hotkey": NodeType(
        key="steer_hotkey",
        display_name="Hotkey",
        category="computer_use_gui",
        node_class="deterministic",
        description="Send a keyboard shortcut (e.g. 'cmd+s', 'cmd+tab').",
        input_schema={
            "keys": {"type": "string", "required": True, "description": "Key combination (e.g. 'cmd+s')"},
        },
        output_schema={"success": {"type": "boolean"}},
    ),
    "steer_scroll": NodeType(
        key="steer_scroll",
        display_name="Scroll",
        category="computer_use_gui",
        node_class="deterministic",
        description="Scroll in a direction within an app.",
        input_schema={
            "direction": {"type": "string", "default": "down", "enum": ["up", "down", "left", "right"]},
            "amount": {"type": "integer", "default": 3},
            "target": {"type": "string", "default": ""},
        },
        output_schema={"success": {"type": "boolean"}},
    ),
    "steer_drag": NodeType(
        key="steer_drag",
        display_name="Drag",
        category="computer_use_gui",
        node_class="deterministic",
        description="Drag from one point to another.",
        input_schema={
            "start_x": {"type": "integer", "required": True},
            "start_y": {"type": "integer", "required": True},
            "end_x": {"type": "integer", "required": True},
            "end_y": {"type": "integer", "required": True},
        },
        output_schema={"success": {"type": "boolean"}},
    ),
    "steer_focus": NodeType(
        key="steer_focus",
        display_name="Focus App",
        category="computer_use_gui",
        node_class="deterministic",
        description="Activate and bring a specific app to the foreground.",
        input_schema={
            "app": {"type": "string", "required": True, "description": "App name to focus"},
        },
        output_schema={"screenshot_base64": {"type": "string"}, "success": {"type": "boolean"}},
    ),
    "steer_find": NodeType(
        key="steer_find",
        display_name="Find Element",
        category="computer_use_gui",
        node_class="deterministic",
        description="Locate a UI element on screen by text or description.",
        input_schema={
            "search_text": {"type": "string", "required": True},
        },
        output_schema={"found": {"type": "boolean"}, "coordinates": {"type": "object"}},
    ),
    "steer_wait": NodeType(
        key="steer_wait",
        display_name="Wait For",
        category="computer_use_gui",
        node_class="deterministic",
        description="Wait for text to appear on screen (with timeout).",
        input_schema={
            "search_text": {"type": "string", "required": True},
            "timeout": {"type": "integer", "default": 10},
        },
        output_schema={"condition_met": {"type": "boolean"}},
    ),
    "steer_clipboard": NodeType(
        key="steer_clipboard",
        display_name="Clipboard",
        category="computer_use_gui",
        node_class="deterministic",
        description="Read from or write to the system clipboard.",
        input_schema={
            "action": {"type": "string", "default": "read", "enum": ["read", "write"]},
            "text": {"type": "string", "default": ""},
        },
        output_schema={"clipboard": {"type": "string"}},
    ),
    "steer_apps": NodeType(
        key="steer_apps",
        display_name="List Apps",
        category="computer_use_gui",
        node_class="deterministic",
        description="List all running applications.",
        input_schema={},
        output_schema={"apps": {"type": "array"}, "app_count": {"type": "integer"}},
    ),
}

# --- Drive node types (terminal automation) ---

DRIVE_NODES: dict[str, NodeType] = {
    "drive_session": NodeType(
        key="drive_session",
        display_name="Terminal Session",
        category="computer_use_terminal",
        node_class="deterministic",
        description="Create, list, or manage tmux sessions.",
        input_schema={
            "action": {"type": "string", "default": "create", "enum": ["create", "list", "kill"]},
            "session": {"type": "string", "default": ""},
            "layout": {"type": "string", "default": ""},
        },
        output_schema={"session": {"type": "string"}, "sessions": {"type": "array"}},
    ),
    "drive_run": NodeType(
        key="drive_run",
        display_name="Run Command",
        category="computer_use_terminal",
        node_class="deterministic",
        description="Execute a command in a tmux pane with sentinel pattern for reliable completion detection.",
        input_schema={
            "command": {"type": "string", "required": True},
            "session": {"type": "string", "default": ""},
            "timeout": {"type": "integer", "default": 30},
        },
        output_schema={"text": {"type": "string"}, "exit_code": {"type": "integer"}},
    ),
    "drive_send": NodeType(
        key="drive_send",
        display_name="Send Keys",
        category="computer_use_terminal",
        node_class="deterministic",
        description="Send raw keystrokes to a tmux pane (for interactive programs).",
        input_schema={
            "keys": {"type": "string", "required": True},
            "session": {"type": "string", "default": ""},
        },
        output_schema={"success": {"type": "boolean"}},
    ),
    "drive_logs": NodeType(
        key="drive_logs",
        display_name="Capture Logs",
        category="computer_use_terminal",
        node_class="deterministic",
        description="Capture the current output of a tmux pane.",
        input_schema={
            "session": {"type": "string", "default": ""},
            "lines": {"type": "integer", "default": 100},
        },
        output_schema={"text": {"type": "string"}, "line_count": {"type": "integer"}},
    ),
    "drive_poll": NodeType(
        key="drive_poll",
        display_name="Poll Sentinel",
        category="computer_use_terminal",
        node_class="deterministic",
        description="Wait for a sentinel marker indicating a previously sent command has completed.",
        input_schema={
            "token": {"type": "string", "required": True},
            "session": {"type": "string", "default": ""},
            "timeout": {"type": "integer", "default": 30},
        },
        output_schema={"completed": {"type": "boolean"}, "exit_code": {"type": "integer"}},
    ),
    "drive_fanout": NodeType(
        key="drive_fanout",
        display_name="Parallel Commands",
        category="computer_use_terminal",
        node_class="deterministic",
        description="Execute commands across multiple tmux panes in parallel.",
        input_schema={
            "commands": {"type": "array", "required": True, "description": "Array of command strings"},
            "session": {"type": "string", "default": ""},
            "layout": {"type": "string", "default": "tiled"},
        },
        output_schema={"results": {"type": "array"}, "command_count": {"type": "integer"}},
    ),
}

# --- Computer use agent node types ---

CU_AGENT_NODES: dict[str, NodeType] = {
    "cu_planner": NodeType(
        key="cu_planner",
        display_name="CU Planner",
        category="computer_use_agent",
        node_class="agent",
        description="Plan the next sequence of GUI/terminal actions given an objective and screen state.",
        input_schema={
            "objective": {"type": "string", "required": True},
        },
        output_schema={"plan": {"type": "array"}, "step_count": {"type": "integer"}},
    ),
    "cu_analyzer": NodeType(
        key="cu_analyzer",
        display_name="CU Analyzer",
        category="computer_use_agent",
        node_class="agent",
        description="Analyze a screenshot or OCR results to extract relevant information about the screen state.",
        input_schema={
            "focus": {"type": "string", "default": "", "description": "What to focus the analysis on"},
        },
        output_schema={"analysis": {"type": "object"}, "text": {"type": "string"}},
    ),
    "cu_verifier": NodeType(
        key="cu_verifier",
        display_name="CU Verifier",
        category="computer_use_agent",
        node_class="agent",
        description="Verify if an objective was achieved by reviewing the current screen state.",
        input_schema={
            "objective": {"type": "string", "required": True},
            "expected": {"type": "string", "default": ""},
        },
        output_schema={"success": {"type": "boolean"}, "confidence": {"type": "number"}},
    ),
    "cu_error_handler": NodeType(
        key="cu_error_handler",
        display_name="CU Error Handler",
        category="computer_use_agent",
        node_class="agent",
        description="Analyze errors and suggest recovery actions for self-healing flows.",
        input_schema={
            "error": {"type": "string", "required": True},
            "original_action": {"type": "string", "default": ""},
        },
        output_schema={"recoverable": {"type": "boolean"}, "recovery_actions": {"type": "array"}},
    ),
}

# --- Agent Control node types (agent-on-agent orchestration) ---

AGENT_CONTROL_NODES: dict[str, NodeType] = {
    "agent_spawn": NodeType(
        key="agent_spawn",
        display_name="Spawn Agent",
        category="agent_control",
        node_class="deterministic",
        description="Spawn a coding agent (Claude Code, Codex, Gemini CLI, Aider) in a tmux session.",
        input_schema={
            "backend": {"type": "string", "default": "claude-code", "enum": ["claude-code", "codex-cli", "gemini-cli", "aider", "custom"]},
            "working_directory": {"type": "string", "default": ""},
            "env_vars": {"type": "object", "default": {}},
        },
        output_schema={"session": {"type": "string"}, "backend": {"type": "string"}, "status": {"type": "string"}},
    ),
    "agent_prompt": NodeType(
        key="agent_prompt",
        display_name="Prompt Agent",
        category="agent_control",
        node_class="deterministic",
        description="Send a task prompt to a running coding agent.",
        input_schema={
            "session": {"type": "string", "required": True},
            "prompt": {"type": "string", "required": True},
        },
        output_schema={"prompt_sent": {"type": "boolean"}, "prompt_length": {"type": "integer"}},
    ),
    "agent_monitor": NodeType(
        key="agent_monitor",
        display_name="Monitor Agent",
        category="agent_control",
        node_class="deterministic",
        description="Capture the current output of a running coding agent.",
        input_schema={
            "session": {"type": "string", "required": True},
            "lines": {"type": "integer", "default": 100},
        },
        output_schema={"text": {"type": "string"}, "line_count": {"type": "integer"}},
    ),
    "agent_wait": NodeType(
        key="agent_wait",
        display_name="Wait for Agent",
        category="agent_control",
        node_class="deterministic",
        description="Wait for a spawned coding agent to complete its task.",
        input_schema={
            "session": {"type": "string", "required": True},
            "timeout": {"type": "integer", "default": 300},
            "completion_pattern": {"type": "string", "default": ""},
        },
        output_schema={"completed": {"type": "boolean"}, "elapsed_seconds": {"type": "integer"}, "text": {"type": "string"}},
    ),
    "agent_stop": NodeType(
        key="agent_stop",
        display_name="Stop Agent",
        category="agent_control",
        node_class="deterministic",
        description="Stop a running coding agent and clean up its tmux session.",
        input_schema={
            "session": {"type": "string", "required": True},
        },
        output_schema={"stopped": {"type": "boolean"}},
    ),
    "agent_result": NodeType(
        key="agent_result",
        display_name="Agent Result",
        category="agent_control",
        node_class="deterministic",
        description="Extract and parse the final result from a completed agent session.",
        input_schema={
            "session": {"type": "string", "required": True},
            "output_format": {"type": "string", "default": "text", "enum": ["text", "json", "diff"]},
        },
        output_schema={"text": {"type": "string"}, "parsed": {"type": "object"}, "length": {"type": "integer"}},
    ),
}

# --- Recording control node type ---

RECORDING_NODES: dict[str, NodeType] = {
    "recording_control": NodeType(
        key="recording_control",
        display_name="Recording Control",
        category="computer_use_gui",
        node_class="deterministic",
        description="Start or stop screen recording during a blueprint run.",
        input_schema={
            "action": {"type": "string", "default": "start", "enum": ["start", "stop"]},
            "quality": {"type": "string", "default": "medium", "enum": ["low", "medium", "high"]},
        },
        output_schema={"recording_path": {"type": "string"}, "status": {"type": "string"}},
    ),
}

# Combined registry
NODE_REGISTRY: dict[str, NodeType] = {
    **DETERMINISTIC_NODES,
    **AGENT_NODES,
    **STEER_NODES,
    **DRIVE_NODES,
    **CU_AGENT_NODES,
    **AGENT_CONTROL_NODES,
    **RECORDING_NODES,
}


def get_node_type(key: str) -> NodeType | None:
    """Look up a node type by key."""
    return NODE_REGISTRY.get(key)


def list_node_types(category: str | None = None) -> list[dict]:
    """List all node types, optionally filtered by category."""
    types = list(NODE_REGISTRY.values())
    if category:
        types = [t for t in types if t.category == category]
    return [
        {
            "key": t.key,
            "display_name": t.display_name,
            "category": t.category,
            "node_class": t.node_class,
            "description": t.description,
            "input_schema": t.input_schema,
            "output_schema": t.output_schema,
        }
        for t in types
    ]
