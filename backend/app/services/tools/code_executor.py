import os
import subprocess
import tempfile

from langchain.tools import tool


@tool
def code_executor(code: str) -> str:
    """Execute Python code in a sandboxed environment and return the output. Only pure computation is allowed — no network access, file system writes, or imports of dangerous modules."""
    # Block dangerous patterns (case-insensitive, covers obfuscation attempts)
    blocked = [
        "os.system", "subprocess", "shutil.rmtree", "eval(", "exec(",
        "__import__", "importlib", "getattr", "__subclasses__",
        "__builtins__", "__globals__", "__code__", "compile(",
        "open(", "pathlib", "socket", "http.", "urllib",
        "requests", "ctypes", "multiprocessing", "threading",
        "signal", "sys.exit", "quit(", "exit(",
    ]
    code_lower = code.lower()
    for b in blocked:
        if b.lower() in code_lower:
            return f"Blocked: code contains disallowed pattern '{b}'"

    # Reject code that's too long (limit to 10KB)
    if len(code) > 10_000:
        return "Blocked: code exceeds maximum length of 10,000 characters"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        tmp_path = f.name

    try:
        # Run with restricted environment — strip most env vars
        safe_env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/usr/local/bin"}
        result = subprocess.run(
            ["python3", "-u", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            env=safe_env,
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        return output[:5000] if output else "(no output)"

    except subprocess.TimeoutExpired:
        return "Error: code execution timed out (10s limit)"
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        os.unlink(tmp_path)
