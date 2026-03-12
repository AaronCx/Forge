"""Agent node executors — LLM-powered steps that require judgment."""

import json
from typing import Any

from app.providers.registry import provider_registry


async def _llm_call(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = "",
    json_mode: bool = False,
    temperature: float = 0,
) -> dict[str, Any]:
    """Make an LLM call via the provider registry and return content + token usage."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    resolved_model = model or None  # None → registry default

    response = await provider_registry.complete(
        messages=messages,
        model=resolved_model,
        temperature=temperature,
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


async def execute_llm_generate(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """General-purpose LLM call with system and user prompt."""
    system_prompt = config.get("system_prompt", "You are a helpful assistant.")
    user_prompt = config.get("user_prompt", "")

    # Build user prompt from upstream context + explicit prompt
    context_parts = []
    for key in ("text", "rendered", "chunks", "formatted"):
        if key in inputs:
            val = inputs[key]
            if isinstance(val, list):
                context_parts.append("\n\n".join(str(c) for c in val))
            else:
                context_parts.append(str(val))

    full_prompt = user_prompt
    if context_parts:
        context = "\n\n---\n\n".join(context_parts)
        full_prompt = f"{context}\n\n{user_prompt}" if user_prompt else context

    result = await _llm_call(system_prompt, full_prompt, model=config.get("model", ""))
    return {"text": result["content"], "tokens": result["total_tokens"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "model": result["model"], "provider": result["provider"]}


async def execute_llm_summarize(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Summarize input text with configurable length."""
    text = config.get("text") or inputs.get("text", "")
    max_length = config.get("max_length", "medium")

    length_map = {
        "short": "2-3 sentences",
        "medium": "1-2 paragraphs",
        "long": "3-4 paragraphs with key details",
    }
    length_instruction = length_map.get(max_length, length_map["medium"])

    system_prompt = (
        f"Summarize the following text in {length_instruction}. "
        "Include key points, action items if any, and important dates/deadlines."
    )

    # Handle chunked input
    if isinstance(text, list):
        text = "\n\n".join(str(c) for c in text)

    result = await _llm_call(system_prompt, text[:8000], model=config.get("model", ""))
    return {"summary": result["content"], "text": result["content"],
            "tokens": result["total_tokens"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "model": result["model"], "provider": result["provider"]}


async def execute_llm_extract(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract structured data from text into a defined schema."""
    text = config.get("text") or inputs.get("text", "")
    extraction_schema = config.get("extraction_schema", {})

    if isinstance(text, list):
        text = "\n\n".join(str(c) for c in text)

    schema_desc = ""
    if extraction_schema:
        schema_desc = f"\n\nExtract data matching this schema:\n{json.dumps(extraction_schema, indent=2)}"

    system_prompt = (
        "You are a data extraction expert. Extract all structured data from the given text. "
        "Return a valid JSON object with fields: entities (people, organizations, locations), "
        "dates, monetary_amounts, key_facts, and any other structured data."
        f"{schema_desc}"
    )

    result = await _llm_call(system_prompt, text[:8000], json_mode=True, model=config.get("model", ""))

    try:
        extracted = json.loads(result["content"])
    except json.JSONDecodeError:
        extracted = {"raw": result["content"]}

    return {"extracted": extracted, "text": json.dumps(extracted),
            "tokens": result["total_tokens"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "model": result["model"], "provider": result["provider"]}


async def execute_llm_review(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Review code or text and return feedback with severity ratings."""
    content = config.get("content") or inputs.get("text", "")
    review_type = config.get("review_type", "code")

    if isinstance(content, list):
        content = "\n\n".join(str(c) for c in content)

    prompts = {
        "code": (
            "Review the following code for bugs, security issues, performance problems, "
            "and improvements. Return a JSON array of findings, each with: "
            '"severity" (critical/high/medium/low), "category", "description", "suggestion".'
        ),
        "text": (
            "Review the following text for clarity, grammar, factual accuracy, and "
            "completeness. Return a JSON array of findings, each with: "
            '"severity" (critical/high/medium/low), "category", "description", "suggestion".'
        ),
        "security": (
            "Perform a security review of the following code. Look for injection risks, "
            "auth issues, data exposure, and OWASP top 10 vulnerabilities. Return a JSON array of findings."
        ),
    }

    system_prompt = prompts.get(review_type, prompts["code"])
    result = await _llm_call(system_prompt, content[:8000], json_mode=True, model=config.get("model", ""))

    try:
        parsed = json.loads(result["content"])
        feedback = parsed.get("findings", parsed) if isinstance(parsed, dict) else parsed
    except json.JSONDecodeError:
        feedback = [{"severity": "info", "description": result["content"]}]

    return {"feedback": feedback, "text": json.dumps(feedback),
            "tokens": result["total_tokens"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "model": result["model"], "provider": result["provider"]}


async def execute_llm_implement(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Given a task description and context, generate code."""
    task = config.get("task") or inputs.get("text", "")
    language = config.get("language", "python")
    context = config.get("context") or inputs.get("rendered", "")

    system_prompt = (
        f"You are an expert {language} developer. Implement the requested feature. "
        "Write clean, well-structured code with appropriate error handling. "
        "Return only the code, no explanations."
    )

    user_prompt = task
    if context:
        user_prompt = f"Context:\n{context}\n\nTask:\n{task}"

    result = await _llm_call(system_prompt, user_prompt, model=config.get("model", ""))
    return {"code": result["content"], "text": result["content"],
            "tokens": result["total_tokens"],
            "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"],
            "model": result["model"], "provider": result["provider"]}


# Executor dispatch table
AGENT_EXECUTORS = {
    "llm_generate": execute_llm_generate,
    "llm_summarize": execute_llm_summarize,
    "llm_extract": execute_llm_extract,
    "llm_review": execute_llm_review,
    "llm_implement": execute_llm_implement,
}
