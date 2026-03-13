"""Input sanitization utilities for XSS and injection prevention."""

from __future__ import annotations

import html
import re


def sanitize_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS.

    Args:
        text: Raw user input that may contain HTML/script tags.

    Returns:
        HTML-escaped string safe for rendering.
    """
    return html.escape(text, quote=True)


def strip_html_tags(text: str) -> str:
    """Remove all HTML tags from text.

    Args:
        text: Text that may contain HTML tags.

    Returns:
        Text with all HTML tags removed.
    """
    return re.sub(r"<[^>]+>", "", text)


def sanitize_path(path: str) -> str:
    """Sanitize a file path to prevent path traversal attacks.

    Args:
        path: User-supplied file path or name.

    Returns:
        Sanitized path with traversal sequences removed.

    Raises:
        ValueError: If the path contains traversal attempts.
    """
    # Block path traversal patterns
    if ".." in path or path.startswith("/") or path.startswith("\\"):
        raise ValueError(
            "Path contains traversal characters. "
            "Relative paths with '..' and absolute paths are not allowed."
        )

    # Remove null bytes
    path = path.replace("\x00", "")

    # Normalize separators
    path = path.replace("\\", "/")

    return path
