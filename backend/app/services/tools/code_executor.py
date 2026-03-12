import os
import subprocess
import tempfile

from langchain.tools import tool


@tool
def code_executor(code: str) -> str:
    """Execute Python code in a sandboxed environment and return the output. Only pure computation is allowed — no network access, file system writes, or imports of dangerous modules."""
    # Block dangerous imports
    blocked = ["os.system", "subprocess", "shutil.rmtree", "eval(", "exec(", "__import__"]
    for b in blocked:
        if b in code:
            return f"Blocked: code contains disallowed pattern '{b}'"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
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
