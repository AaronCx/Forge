"""Eval grading methods — score agent outputs against expected results."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.providers.registry import provider_registry


def _ocr_image_file(path: str) -> str:
    """OCR an image file's text via pytesseract; '' if OCR isn't available."""
    try:
        import pytesseract
        from PIL import Image

        return str(pytesseract.image_to_string(Image.open(path)))
    except Exception:
        return ""


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
    is_regex = bool(config.get("regex"))
    flags = 0 if case_sensitive else re.IGNORECASE

    matches = 0
    for pattern in patterns:
        if is_regex:
            # Lowercasing a regex source corrupts it (\D→\d, [A-Z]→[a-z]); use the
            # IGNORECASE flag against the original text for case-insensitive matching.
            if re.search(pattern, actual, flags):
                matches += 1
        else:
            check_pattern = pattern if case_sensitive else pattern.lower()
            if check_pattern in check_actual:
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
            # bool is a subclass of int, so a JSON true/false would wrongly pass
            # an integer/number type — reject it explicitly.
            if expected_type in ("integer", "number") and isinstance(value, bool):
                errors.append(f"Key '{key}' expected {expected_type}, got boolean")
            elif expected_cls and not isinstance(value, expected_cls):  # type: ignore[arg-type]
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
            # The judge may return score as a string ("0.9"); coerce before any
            # numeric comparison so `score >= 0.7` can't raise a TypeError.
            try:
                score_val = float(result.get("score", 0))
            except (TypeError, ValueError):
                score_val = 0.0
            return {
                "passed": bool(result.get("passed", score_val >= 0.7)),
                "score": score_val,
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

    if os.environ.get("FORGE_ALLOW_CUSTOM_GRADERS", "").lower() not in ("1", "true"):
        return {
            "passed": False,
            "score": 0.0,
            "method": "custom",
            "error": "Custom graders are disabled. Set FORGE_ALLOW_CUSTOM_GRADERS=1 to enable executing custom grading functions.",
        }

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


def grade_screenshot_match(actual: str, expected: str, config: dict[str, Any]) -> dict[str, Any]:
    """Compare a screenshot against a reference image using structural similarity.

    actual: path to the captured screenshot
    expected: path to the reference screenshot
    config: optional 'threshold' (default 0.8) for similarity score
    """
    threshold = float(config.get("threshold", 0.8))

    try:
        import imagehash
        from PIL import Image

        img_actual = Image.open(actual)
        img_expected = Image.open(expected)

        hash_actual = imagehash.phash(img_actual)
        hash_expected = imagehash.phash(img_expected)

        # Perceptual hash distance (0 = identical, higher = more different)
        distance = hash_actual - hash_expected
        max_distance = 64  # phash returns 64-bit hash
        similarity = 1.0 - (distance / max_distance)

        return {
            "passed": similarity >= threshold,
            "score": round(similarity, 4),
            "method": "screenshot_match",
            "distance": distance,
            "threshold": threshold,
        }
    except ImportError:
        # No bogus file-size heuristic — it has no relation to visual content and
        # would pass dissimilar images. Fail honestly so the gap is visible.
        return {
            "passed": False,
            "score": 0.0,
            "method": "screenshot_match",
            "error": "Pillow/imagehash not installed — cannot compare images",
        }
    except Exception as e:
        return {"passed": False, "score": 0.0, "method": "screenshot_match", "error": str(e)}


def grade_ocr_contains(actual: str, _expected: str, config: dict[str, Any]) -> dict[str, Any]:
    """Run OCR on a screenshot and check if specific text is present.

    actual: path to a screenshot file
    config: 'texts' (array of strings to look for), 'threshold' (fraction required)
    """
    texts = config.get("texts", [])
    if not texts and _expected:
        texts = [_expected]
    threshold = float(config.get("threshold", 1.0))

    if not texts:
        return {"passed": False, "score": 0.0, "method": "ocr_contains", "error": "No texts to check"}

    # If `actual` is an image file, OCR the FILE (the old code ran `steer ocr`
    # with no path, OCR-ing the live screen). Otherwise treat actual as text.
    import os

    if os.path.isfile(actual):
        ocr_text = _ocr_image_file(actual).lower()
        if not ocr_text:
            return {
                "passed": False, "score": 0.0, "method": "ocr_contains",
                "error": "OCR unavailable (install pytesseract+Pillow) for the image file",
            }
    else:
        ocr_text = actual.lower()

    matches = sum(1 for t in texts if t.lower() in ocr_text)
    score = matches / len(texts) if texts else 0.0

    return {
        "passed": score >= threshold,
        "score": round(score, 4),
        "method": "ocr_contains",
        "matched": matches,
        "total": len(texts),
    }


GRADING_METHODS = {
    "exact_match": grade_exact_match,
    "contains": grade_contains,
    "json_schema": grade_json_schema,
    "llm_judge": grade_llm_judge,
    "custom": grade_custom,
    "screenshot_match": grade_screenshot_match,
    "ocr_contains": grade_ocr_contains,
    # "human" is handled separately — it just marks as pending
}
