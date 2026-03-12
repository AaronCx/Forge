from unittest.mock import AsyncMock, patch

import pytest


def test_code_executor_blocks_dangerous_code():
    from app.services.tools.code_executor import code_executor

    result = code_executor.invoke("os.system('rm -rf /')")
    assert "Blocked" in result

    result = code_executor.invoke("subprocess.run(['ls'])")
    assert "Blocked" in result

    result = code_executor.invoke("__import__('os').system('ls')")
    assert "Blocked" in result


def test_code_executor_runs_safe_code():
    from app.services.tools.code_executor import code_executor

    result = code_executor.invoke("print(2 + 2)")
    assert "4" in result


def test_code_executor_handles_timeout():
    from app.services.tools.code_executor import code_executor

    result = code_executor.invoke("import time; time.sleep(20)")
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_web_search_no_api_key():
    with patch.dict("os.environ", {"SERPAPI_KEY": ""}, clear=False):
        from app.services.tools.web_search import web_search
        result = await web_search.ainvoke("test query")
        assert "not configured" in result.lower()


@pytest.mark.asyncio
async def test_data_extractor():
    from app.providers.base import LLMResponse

    mock_response = LLMResponse(
        content='{"entities": ["John"], "dates": ["2024-01-01"]}',
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=20,
        finish_reason="stop",
        latency_ms=50,
        provider="openai",
    )

    with patch("app.services.tools.data_extractor.provider_registry") as mock_registry:
        mock_registry.complete = AsyncMock(return_value=mock_response)

        from app.services.tools.data_extractor import data_extractor
        result = await data_extractor.ainvoke("John was born on January 1, 2024")
        assert "John" in result


@pytest.mark.asyncio
async def test_summarizer():
    from app.providers.base import LLMResponse

    mock_response = LLMResponse(
        content="This is a summary of the text.",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=15,
        finish_reason="stop",
        latency_ms=50,
        provider="openai",
    )

    with patch("app.services.tools.summarizer.provider_registry") as mock_registry:
        mock_registry.complete = AsyncMock(return_value=mock_response)

        from app.services.tools.summarizer import summarizer
        result = await summarizer.ainvoke("A very long text that needs summarizing...")
        assert "summary" in result.lower()
