"""Deterministic node executors — fixed code that runs the same way every time."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

import httpx

from app.services.security.url_validator import validate_url
from app.services.tools.document_reader import document_reader


async def execute_fetch_url(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Fetch a URL and return its text content."""
    url = config.get("url") or inputs.get("url", "")
    if not url:
        raise ValueError("fetch_url: 'url' is required")

    validate_url(url)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        text = resp.text[:50_000]  # Cap at 50KB

    return {"text": text}


async def execute_fetch_document(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract text from a PDF, DOCX, or TXT file."""
    file_url = config.get("file_url") or inputs.get("file_url", "")
    if not file_url:
        raise ValueError("fetch_document: 'file_url' is required")

    validate_url(file_url)

    # Reuse the existing document_reader tool
    result = await document_reader.ainvoke(file_url)
    return {"text": str(result)}


async def execute_run_linter(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Run a linter on code and return results."""
    code = config.get("code") or inputs.get("text", "")
    language = config.get("language", "python")

    if language != "python":
        return {"result": code, "has_errors": False}

    # Use ruff for Python linting (check mode)
    try:
        proc = subprocess.run(
            ["python3", "-m", "ruff", "check", "--stdin-filename=code.py", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        has_errors = proc.returncode != 0
        result = proc.stdout or proc.stderr or "No issues found."
    except (subprocess.TimeoutExpired, FileNotFoundError):
        result = code
        has_errors = False

    return {"result": result, "has_errors": has_errors}


async def execute_json_validator(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Validate data against a JSON schema (simplified validation)."""
    raw = config.get("data") or inputs.get("text", "")
    schema = config.get("schema", {})

    errors: list[str] = []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"Invalid JSON: {e}"], "data": raw}

    # Simple required-field validation
    required = schema.get("required", [])
    if isinstance(data, dict):
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")

    return {"valid": len(errors) == 0, "errors": errors, "data": raw if errors else json.dumps(data)}


async def execute_text_splitter(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Split text into chunks with configurable size and overlap."""
    text = config.get("text") or inputs.get("text", "")
    chunk_size = int(config.get("chunk_size", 2000))
    overlap = int(config.get("overlap", 200))

    if not text:
        return {"chunks": [], "chunk_count": 0}

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start >= len(text):
            break

    return {"chunks": chunks, "chunk_count": len(chunks)}


async def execute_template_renderer(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Render a prompt template with variables from upstream nodes."""
    template = config.get("template", "")
    variables = {**inputs, **config.get("variables", {})}

    # Replace {{variable_name}} patterns
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))

    return {"rendered": rendered}


async def execute_webhook(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Send an HTTP POST to a URL with the current state."""
    url = config.get("url", "")
    if not url:
        raise ValueError("webhook: 'url' is required")

    validate_url(url)

    payload = {**inputs, **config.get("payload", {})}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)

    return {"status_code": resp.status_code, "response": resp.text[:2000]}


async def execute_output_formatter(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Format the final result as JSON, markdown, or plain text."""
    data = config.get("data") or inputs.get("text", "") or inputs.get("rendered", "")
    fmt = config.get("format", "markdown")

    if fmt == "json":
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
            formatted = json.dumps(parsed, indent=2)
        except (json.JSONDecodeError, TypeError):
            formatted = json.dumps({"result": str(data)}, indent=2)
    elif fmt == "markdown":
        formatted = str(data)
    else:
        # Plain text — strip markdown formatting
        formatted = re.sub(r"[#*_`>]", "", str(data))

    return {"formatted": formatted}


# Executor dispatch table
async def execute_approval_gate(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Pause execution for human approval.

    Creates an approval request and raises an exception to pause the run.
    The blueprint engine handles this by pausing the run until approved.
    """
    from app.services.evals.approvals import approval_service

    message = config.get("message", "Please review and approve to continue.")
    run_id = inputs.get("_run_id", "")
    node_id = inputs.get("_node_id", "")
    user_id = inputs.get("_user_id", "")

    if run_id and user_id:
        # Check if already approved
        existing = await approval_service.get_approval_for_run(run_id, node_id)
        if existing and existing["status"] == "approved":
            return {
                "approved": True,
                "feedback": existing.get("feedback", ""),
                "text": f"Approved: {existing.get('feedback', '')}",
            }
        if existing and existing["status"] == "rejected":
            raise ValueError(f"Approval rejected: {existing.get('feedback', '')}")

        # Create new approval request
        context = {
            "message": message,
            "upstream_data": {k: v for k, v in inputs.items() if not k.startswith("_")},
        }
        await approval_service.create_approval(
            user_id=user_id,
            blueprint_run_id=run_id,
            node_id=node_id,
            context=context,
        )

    raise ValueError("APPROVAL_PENDING: Execution paused awaiting human approval")


async def execute_knowledge_retrieval(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Retrieve relevant chunks from a knowledge collection via semantic search."""
    from app.services.knowledge.knowledge_service import knowledge_service

    collection_id = config.get("collection_id") or inputs.get("collection_id", "")
    query = config.get("query") or inputs.get("query", "")
    top_k = config.get("top_k", 5)
    user_id = config.get("_user_id", "")

    if not collection_id or not query:
        raise ValueError("knowledge_retrieval: 'collection_id' and 'query' are required")

    results = await knowledge_service.search(
        user_id=user_id,
        collection_id=collection_id,
        query=query,
        top_k=top_k,
    )

    # Build context string from chunks
    context_parts = []
    for r in results:
        context_parts.append(r.get("content", ""))

    return {
        "chunks": results,
        "context": "\n\n---\n\n".join(context_parts),
    }


DETERMINISTIC_EXECUTORS = {
    "fetch_url": execute_fetch_url,
    "fetch_document": execute_fetch_document,
    "run_linter": execute_run_linter,
    "json_validator": execute_json_validator,
    "text_splitter": execute_text_splitter,
    "template_renderer": execute_template_renderer,
    "webhook": execute_webhook,
    "output_formatter": execute_output_formatter,
    "approval_gate": execute_approval_gate,
    "knowledge_retrieval": execute_knowledge_retrieval,
}
