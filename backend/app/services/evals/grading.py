"""Eval grading methods — score agent outputs against expected results."""

from __future__ import annotations

import json
import re
from typing import Any

from app.providers.registry import provider_registry


def grade_exact_match(actual: str, expected: str, _config: dict[str, Any]) -> dict[str, Any]:
    """Exact string match (case-sensitive by default)."""
    case_sensitive = _config.get("case_sensitive", True)
    if not case_sensitive:
        passed = actual.strip().lower() == expected.strip().lower()
    else:
        passed = actual.strip() == expected.strip()
    return {"passed": passed, "score": 1.0 if passed else 0.0, "method": "exact_match"}


def grade_contains(actual: str, expected: str, config: dict[str, Any]) -> dict[str, Any]:
    """Check if output contains expected strings or patterns."""
    patterns = config.get("patterns", [])
    if not patterns and expected:
        patterns = [expected]

    case_sensitive = config.get("case_sensitive", False)
    check_actual = actual if case_sensitive else actual.lower()

    matches = 0
    for pattern in patterns:
        check_pattern = pattern if case_sensitive else pattern.lower()
        if config.get("regex"):
            if re.search(check_pattern, check_actual):
                matches += 1
        elif check_pattern in check_actual:
            matches += 1

    total = len(patterns) if patterns else 1
    score = matches / total if total > 0 else 0.0
    return {
        "passed": score >= config.get("threshold", 1.0),
        "score": score,
        "method": "contains",
        "matched": matches,
        "total": total,
    }


def grade_json_schema(actual: str, _expected: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate that output conforms to a JSON schema."""
    schema = config.get("schema", {})

    try:
        parsed = json.loads(actual)
    except json.JSONDecodeError:
        return {"passed": False, "score": 0.0, "method": "json_schema", "error": "Invalid JSON"}

    # Simple schema validation (check required keys and types)
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    if not properties and not required:
        # No schema defined — just check it's valid JSON
        return {"passed": True, "score": 1.0, "method": "json_schema"}

    errors = []
    for key in required:
        if key not in parsed:
            errors.append(f"Missing required key: {key}")

    for key, prop_schema in properties.items():
        if key in parsed:
            expected_type = prop_schema.get("type", "")
            value = parsed[key]
            type_map = {
                "string": str, "number": (int, float), "integer": int,
                "boolean": bool, "array": list, "object": dict,
            }
            expected_cls = type_map.get(expected_type)
            if expected_cls and not isinstance(value, expected_cls):  # type: ignore[arg-type]
                errors.append(f"Key '{key}' expected {expected_type}, got {type(value).__name__}")

    score = 1.0 - (len(errors) / max(len(required) + len(properties), 1))
    return {
        "passed": len(errors) == 0,
        "score": max(0.0, score),
        "method": "json_schema",
        "errors": errors,
    }


async def grade_llm_judge(actual: str, expected: str, config: dict[str, Any]) -> dict[str, Any]:
    """Use an LLM to judge the quality of the output."""
    rubric = config.get("rubric", "accuracy, completeness, relevance")
    model = config.get("model")

    system_prompt = (
        "You are an evaluation judge. Grade the following agent output against the expected output. "
        f"Evaluate on these criteria: {rubric}. "
        "Return a JSON object with: score (0.0 to 1.0), passed (boolean), reasoning (string)."
    )
    user_prompt = (
        f"Expected output:\n{expected}\n\n"
        f"Actual output:\n{actual}\n\n"
        "Grade the actual output. Return JSON: {\"score\": ..., \"passed\": ..., \"reasoning\": ...}"
    )

    try:
        response = await provider_registry.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0,
        )

        try:
            result = json.loads(response.content)
            return {
                "passed": result.get("passed", result.get("score", 0) >= 0.7),
                "score": float(result.get("score", 0)),
                "method": "llm_judge",
                "reasoning": result.get("reasoning", ""),
                "judge_tokens": response.input_tokens + response.output_tokens,
            }
        except json.JSONDecodeError:
            # LLM didn't return JSON — try to extract a score
            return {
                "passed": False,
                "score": 0.0,
                "method": "llm_judge",
                "reasoning": response.content,
                "error": "Judge did not return valid JSON",
            }
    except Exception as e:
        return {
            "passed": False,
            "score": 0.0,
            "method": "llm_judge",
            "error": str(e),
        }


def grade_custom(actual: str, expected: str, config: dict[str, Any]) -> dict[str, Any]:
    """Run a custom Python function for grading.

    The function string is evaluated with `actual` and `expected` in scope.
    It should return a dict with 'passed' and 'score'.
    """
    func_str = config.get("function", "")
    if not func_str:
        return {"passed": False, "score": 0.0, "method": "custom", "error": "No function provided"}

    try:
        # Create a restricted namespace
        namespace: dict[str, Any] = {"actual": actual, "expected": expected, "json": json, "re": re}
        exec(func_str, namespace)  # noqa: S102
        result = namespace.get("result", {"passed": False, "score": 0.0})
        return {
            "passed": bool(result.get("passed", False)),
            "score": float(result.get("score", 0.0)),
            "method": "custom",
        }
    except Exception as e:
        return {"passed": False, "score": 0.0, "method": "custom", "error": str(e)}


GRADING_METHODS = {
    "exact_match": grade_exact_match,
    "contains": grade_contains,
    "json_schema": grade_json_schema,
    "llm_judge": grade_llm_judge,
    "custom": grade_custom,
    # "human" is handled separately — it just marks as pending
}
