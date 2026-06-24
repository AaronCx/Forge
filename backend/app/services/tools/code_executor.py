"""Best-effort sandbox for the agent's code-execution tool.

A substring denylist cannot sandbox CPython (aliasing ``open``, ``os.execv``,
dunder introspection, etc. all slip past one). This uses three layers instead:

1. **AST allowlist** — only a fixed set of safe stdlib modules may be imported;
   dangerous builtins (``eval``/``exec``/``open``/``getattr``/...), dangerous
   module names (``os``/``subprocess``/``socket``/...), and dunder attribute
   access are rejected *before* anything runs.
2. **Locked-down subprocess** — ``python3 -I -S -B`` with a minimal environment
   and an empty working directory, separate from the app interpreter.
3. **OS resource limits (POSIX)** — a CPU cap and a zero file-size limit so the
   code cannot grow files or write to disk, on top of the 10s wall-clock limit.
"""

from __future__ import annotations

import ast
import contextlib
import os
import subprocess
import tempfile

from langchain.tools import tool

# Modules safe for pure computation. Anything else is rejected at parse time.
_SAFE_MODULES = {
    "math", "cmath", "statistics", "random", "secrets", "decimal", "fractions",
    "json", "re", "datetime", "time", "calendar", "itertools", "functools",
    "operator", "collections", "heapq", "bisect", "array", "string", "textwrap",
    "unicodedata", "numbers", "typing", "dataclasses", "enum", "copy", "pprint",
    "uuid", "hashlib", "hmac",
}

# Builtins that defeat the sandbox if reachable.
_BLOCKED_NAMES = {
    "eval", "exec", "compile", "open", "input", "breakpoint", "__import__",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "memoryview", "help", "exit", "quit", "copyright", "credits", "license",
}

# Dangerous module-like identifiers — blocked even when referenced without an
# import (e.g. a bare ``os.system(...)`` against an injected name).
_BLOCKED_ROOTS = {
    "os", "sys", "subprocess", "socket", "shutil", "importlib", "ctypes",
    "multiprocessing", "threading", "signal", "pickle", "marshal", "shelve",
    "pty", "pathlib", "io", "builtins", "gc", "inspect", "platform", "resource",
    "fcntl", "mmap", "tempfile", "glob", "requests", "httpx", "urllib", "http",
    "ftplib", "smtplib", "telnetlib", "asyncio", "webbrowser", "base64",
    "codecs", "binascii",
}

_MAX_BYTES = 10_000


def _reject_reason(code: str) -> str | None:
    """Return a human-readable reason if the AST is unsafe, else ``None``."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"could not parse code ({exc.msg})"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in _SAFE_MODULES:
                    return f"import of '{alias.name}' is not allowed"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in _SAFE_MODULES:
                return f"import from '{node.module}' is not allowed"
        elif isinstance(node, ast.Name):
            if node.id in _BLOCKED_NAMES or node.id in _BLOCKED_ROOTS:
                return f"use of '{node.id}' is not allowed"
        elif (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr.endswith("__")
        ):
            return f"access to dunder attribute '{node.attr}' is not allowed"
    return None


def _posix_limits() -> None:  # pragma: no cover - runs in the forked child
    """Apply OS resource limits in the child before exec (POSIX only)."""
    import resource

    for res, limit in (
        (resource.RLIMIT_CPU, 11),       # CPU-seconds backstop to the wall timeout
        (resource.RLIMIT_FSIZE, 0),      # cannot create/grow files on disk
    ):
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(res, (limit, limit))


@tool
def code_executor(code: str) -> str:
    """Execute Python code for pure computation and return its output. Imports are restricted to a safe stdlib allowlist; file, network, process, and introspection access are blocked."""
    # Reject oversized payloads before parsing.
    if len(code) > _MAX_BYTES:
        return "Blocked: code exceeds maximum length of 10,000 characters"

    reason = _reject_reason(code)
    if reason is not None:
        return f"Blocked: {reason}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        tmp_path = f.name

    workdir = tempfile.mkdtemp(prefix="forge-exec-")
    try:
        # Isolated interpreter: ignore env vars (-I), no site (-S), no bytecode
        # (-B), unbuffered (-u). Minimal env; run from an empty directory.
        safe_env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/usr/local/bin"}
        result = subprocess.run(
            ["python3", "-I", "-S", "-B", "-u", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            env=safe_env,
            cwd=workdir,
            preexec_fn=_posix_limits if os.name == "posix" else None,  # noqa: PLW1509
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        return output[:5000] if output else "(no output)"

    except subprocess.TimeoutExpired:
        return "Error: code execution timed out (10s limit)"
    except Exception as e:  # noqa: BLE001 - the tool must always return a string
        return f"Error: {str(e)}"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        with contextlib.suppress(OSError):
            os.rmdir(workdir)
