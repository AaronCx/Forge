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

# Combined registry
NODE_REGISTRY: dict[str, NodeType] = {**DETERMINISTIC_NODES, **AGENT_NODES}


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
