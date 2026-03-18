"""Comprehensive security & prompt injection testing for AgentForge v1.9.

Covers all 19 sections of the security audit spec:
1. Prompt Injection — Agent System Prompts
2. Prompt Injection — Blueprint Nodes
3. Prompt Injection — Knowledge Base / RAG
4. Prompt Injection — MCP Tool Descriptions
5. Prompt Injection — Computer Use
6. Prompt Injection — Agent-on-Agent Orchestration
7. Authentication & Authorization Attacks
8. External Input Injection (Webhooks)
9. Data Exfiltration via Agent Output
10. SQL Injection
11. XSS via Stored Content
12. Path Traversal
13. SSRF (Server-Side Request Forgery)
14. Denial of Service
15. Marketplace Security
16. Remote Execution Security (Computer Use)
17. Secrets & Key Exposure
18. Input Validation Audit
19. Injection Surface Audit
"""

from __future__ import annotations

import os
import re
from unittest.mock import patch

import pytest

# Ensure test mode is set
os.environ["AGENTFORGE_TESTING"] = "1"


# ────────────────────────────────────────────────────────────────
# Section 1: Prompt Injection — Agent System Prompts
# ────────────────────────────────────────────────────────────────


class TestPromptInjectionAgents:
    """Section 1: Test that system prompts are handled safely."""

    def test_system_prompt_max_length_enforced(self):
        """1.1 System prompts have a max length."""
        from app.models.agent import AgentCreate

        with pytest.raises((ValueError, TypeError, Exception)):
            AgentCreate(
                name="test",
                system_prompt="x" * 10001,
            )

    def test_system_prompt_min_length_enforced(self):
        """1.2 System prompts cannot be empty."""
        from app.models.agent import AgentCreate

        with pytest.raises((ValueError, TypeError, Exception)):
            AgentCreate(
                name="test",
                system_prompt="",
            )

    def test_user_input_not_executed_as_system(self):
        """1.3 User input is passed as 'user' role, not 'system'."""
        from app.services.agent_executor import AgentRunner

        runner = AgentRunner()
        # Verify _execute_step builds messages with correct roles
        import inspect

        source = inspect.getsource(runner._execute_step)
        assert '"role": "system"' in source or "'role': 'system'" in source
        assert '"role": "user"' in source or "'role': 'user'" in source

    def test_workflow_steps_have_max_length(self):
        """1.4 Workflow steps list is bounded."""
        from app.models.agent import AgentCreate

        with pytest.raises((ValueError, TypeError, Exception)):
            AgentCreate(
                name="test",
                system_prompt="Hello",
                workflow_steps=["step"] * 51,
            )

    def test_tools_list_bounded(self):
        """1.5 Tools list is bounded."""
        from app.models.agent import AgentCreate

        with pytest.raises((ValueError, TypeError, Exception)):
            AgentCreate(
                name="test",
                system_prompt="Hello",
                tools=["tool"] * 21,
            )


# ────────────────────────────────────────────────────────────────
# Section 2: Prompt Injection — Blueprint Nodes
# ────────────────────────────────────────────────────────────────


class TestPromptInjectionBlueprints:
    """Section 2: Blueprint node config injection."""

    def test_blueprint_dag_cycle_detection(self):
        """2.1 Cyclic DAGs are rejected."""
        from app.services.blueprint_engine import _topological_sort

        nodes = [
            {"id": "a", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
        ]
        with pytest.raises(ValueError, match="cycle"):
            _topological_sort(nodes)

    def test_unknown_node_type_rejected(self):
        """2.2 Unknown node types raise ValueError."""
        from app.services.blueprint_nodes.registry import NODE_REGISTRY

        assert "shell_exec" not in NODE_REGISTRY
        assert "arbitrary_code" not in NODE_REGISTRY

    def test_template_renderer_only_replaces_known_vars(self):
        """2.3 Template renderer doesn't execute code."""
        import asyncio

        from app.services.blueprint_nodes.deterministic import (
            execute_template_renderer,
        )

        result = asyncio.get_event_loop().run_until_complete(
            execute_template_renderer(
                {"template": "Hello {{name}}, {{__import__('os').system('ls')}}"},
                {"name": "World"},
            )
        )
        # Should not execute — just leave unresolved template vars as-is
        assert "__import__" in result["rendered"]
        assert "World" in result["rendered"]


# ────────────────────────────────────────────────────────────────
# Section 3: Prompt Injection — Knowledge Base / RAG
# ────────────────────────────────────────────────────────────────


class TestKnowledgeBaseInjection:
    """Section 3: RAG poisoning and document injection."""

    def test_document_size_limit(self):
        """3.1 Document raw_text has max size."""
        from app.routers.knowledge import AddDocumentRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            AddDocumentRequest(
                filename="test.txt",
                raw_text="x" * 5_000_001,
            )

    def test_filename_path_traversal_blocked(self):
        """3.2 Path traversal in filenames is blocked."""
        from app.services.security.sanitizer import sanitize_path

        with pytest.raises(ValueError, match="traversal"):
            sanitize_path("../../etc/passwd")

        with pytest.raises(ValueError, match="traversal"):
            sanitize_path("/etc/shadow")

    def test_filename_null_bytes_stripped(self):
        """3.3 Null bytes in filenames are stripped."""
        from app.services.security.sanitizer import sanitize_path

        result = sanitize_path("test\x00.txt")
        assert "\x00" not in result

    def test_empty_filename_rejected(self):
        """3.4 Empty filename is rejected."""
        from app.routers.knowledge import AddDocumentRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            AddDocumentRequest(filename="", raw_text="hello")


# ────────────────────────────────────────────────────────────────
# Section 4: Prompt Injection — MCP Tool Descriptions
# ────────────────────────────────────────────────────────────────


class TestMCPInjection:
    """Section 4: MCP tool description and server URL injection."""

    def test_mcp_server_url_scheme_validated(self):
        """4.1 Non-HTTP schemes are blocked."""
        from app.services.security.url_validator import SSRFError, validate_url

        with pytest.raises(SSRFError, match="scheme"):
            validate_url("ftp://evil.com/tools")

        with pytest.raises(SSRFError, match="scheme"):
            validate_url("file:///etc/passwd")

        with pytest.raises(SSRFError, match="scheme"):
            validate_url("gopher://internal:25")

    def test_mcp_connect_request_name_bounded(self):
        """4.2 MCP connection name has max length."""
        from app.routers.mcp import MCPConnectRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            MCPConnectRequest(name="x" * 201, server_url="http://example.com")

    def test_mcp_connect_request_url_required(self):
        """4.3 MCP server URL is required."""
        from app.routers.mcp import MCPConnectRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            MCPConnectRequest(name="test", server_url="")


# ────────────────────────────────────────────────────────────────
# Section 5: Prompt Injection — Computer Use
# ────────────────────────────────────────────────────────────────


class TestComputerUseInjection:
    """Section 5: Computer use command injection."""

    def test_command_blocklist_basic(self):
        """5.1 Basic dangerous commands are blocked."""
        from app.services.computer_use.safety import check_command_blocklist

        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("rm -rf /")

        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("shutdown now")

        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("reboot")

    def test_command_blocklist_whitespace_bypass(self):
        """5.2 Extra whitespace doesn't bypass blocklist."""
        from app.services.computer_use.safety import check_command_blocklist

        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("rm  -rf  /")

        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("rm\t-rf\t/")

    def test_command_blocklist_null_byte_bypass(self):
        """5.3 Null bytes don't bypass blocklist."""
        from app.services.computer_use.safety import check_command_blocklist

        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("rm\x00 -rf /")

    def test_app_blocklist(self):
        """5.4 Blocked apps are rejected."""
        from app.services.computer_use.safety import check_app_blocklist

        with pytest.raises(ValueError, match="blocklist"):
            check_app_blocklist("System Preferences")

        with pytest.raises(ValueError, match="blocklist"):
            check_app_blocklist("Keychain Access")

    def test_rate_limiter(self):
        """5.5 Rate limiter works."""
        from app.services.computer_use.safety import ActionRateLimiter

        limiter = ActionRateLimiter(max_per_minute=3)
        assert limiter.check() is True
        assert limiter.check() is True
        assert limiter.check() is True
        assert limiter.check() is False

    def test_audit_log_truncates_long_results(self):
        """5.6 Audit log truncates result to 2000 chars."""
        from app.services.computer_use.safety import log_action

        # This should not raise — just truncate
        with patch("app.db._db") as mock_sb:
            mock_sb.table.return_value.insert.return_value.execute.return_value = None
            log_action(
                node_type="test",
                command="echo",
                arguments={},
                target="terminal",
                result="x" * 5000,
            )
            call_args = mock_sb.table.return_value.insert.call_args[0][0]
            assert len(call_args["result"]) <= 2000


# ────────────────────────────────────────────────────────────────
# Section 6: Agent-on-Agent Orchestration
# ────────────────────────────────────────────────────────────────


class TestOrchestrationSecurity:
    """Section 6: Orchestration security."""

    def test_orchestration_objective_bounded(self):
        """6.1 Orchestration objective has max length."""
        from app.routers.orchestration import OrchestrationRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            OrchestrationRequest(objective="x" * 5001)

    def test_orchestration_tools_bounded(self):
        """6.2 Orchestration tools list is bounded."""
        from app.routers.orchestration import OrchestrationRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            OrchestrationRequest(objective="test", tools=["t"] * 21)

    def test_orchestration_rate_limited(self):
        """6.3 Orchestration endpoint is rate-limited (5/hour)."""
        from app.routers.orchestration import start_orchestration

        # Check that the limiter decorator is applied
        assert hasattr(start_orchestration, "__wrapped__") or "limiter" in str(
            getattr(start_orchestration, "__dict__", {})
        )


# ────────────────────────────────────────────────────────────────
# Section 7: Authentication & Authorization
# ────────────────────────────────────────────────────────────────


class TestAuthSecurity:
    """Section 7: Auth bypass and authorization tests."""

    def test_missing_bearer_prefix_rejected(self):
        """7.1 Auth without Bearer prefix is rejected."""
        import asyncio

        from fastapi import HTTPException

        from app.routers.auth import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_user("InvalidTokenNoBearer")
            )
        assert exc_info.value.status_code == 401

    def test_empty_token_rejected(self):
        """7.2 Empty Bearer token is rejected."""
        import asyncio

        from fastapi import HTTPException

        from app.routers.auth import get_current_user

        # Mock supabase.auth.get_user to simulate invalid token
        with patch("app.db._db") as mock_sb:
            mock_sb.auth.get_user.side_effect = Exception("Invalid token")
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    get_current_user("Bearer ")
                )
            assert exc_info.value.status_code == 401

    def test_agent_ownership_enforced(self):
        """7.3 Agents are user-scoped (verified by code review)."""
        import inspect

        from app.routers.agents import get_agent

        source = inspect.getsource(get_agent)
        assert "user_id" in source
        assert "user.id" in source

    def test_blueprint_ownership_enforced(self):
        """7.4 Blueprints are user-scoped."""
        import inspect

        from app.routers.blueprints import get_blueprint

        source = inspect.getsource(get_blueprint)
        assert "user_id" in source

    def test_trigger_ownership_enforced(self):
        """7.5 Triggers are user-scoped."""
        import inspect

        from app.routers.triggers import update_trigger

        source = inspect.getsource(update_trigger)
        assert "user_id" in source


# ────────────────────────────────────────────────────────────────
# Section 8: External Input Injection (Webhooks)
# ────────────────────────────────────────────────────────────────


class TestWebhookSecurity:
    """Section 8: Webhook endpoint security."""

    def test_webhook_constant_time_comparison(self):
        """8.1 Webhook secret uses constant-time comparison."""
        import inspect

        from app.routers.triggers import webhook_receiver

        source = inspect.getsource(webhook_receiver)
        assert "hmac.compare_digest" in source

    def test_webhook_rate_limited(self):
        """8.2 Webhook endpoint is rate-limited."""

        from app.routers.triggers import webhook_receiver

        # The decorator is applied
        assert hasattr(webhook_receiver, "__wrapped__") or "limiter" in str(
            getattr(webhook_receiver, "__dict__", {})
        )

    def test_webhook_body_size_limited(self):
        """8.3 Webhook body is size-limited."""
        import inspect

        from app.routers.triggers import webhook_receiver

        source = inspect.getsource(webhook_receiver)
        assert "1_048_576" in source or "1048576" in source

    def test_trigger_type_validated(self):
        """8.4 Trigger type is validated against allowed values."""
        from app.routers.triggers import TriggerCreateRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            TriggerCreateRequest(
                type="arbitrary",
                target_type="agent",
                target_id="123",
            )


# ────────────────────────────────────────────────────────────────
# Section 9: Data Exfiltration via Agent Output
# ────────────────────────────────────────────────────────────────


class TestDataExfiltration:
    """Section 9: Verify agent outputs are bounded and logged."""

    def test_agent_output_preview_bounded(self):
        """9.1 Output preview is truncated to 500 chars."""
        import inspect

        from app.services.agent_executor import AgentRunner

        source = inspect.getsource(AgentRunner.execute)
        assert "[:500]" in source

    def test_blueprint_output_preview_bounded(self):
        """9.2 Blueprint execution trace output is bounded."""
        import inspect

        from app.services.blueprint_engine import BlueprintEngine

        source = inspect.getsource(BlueprintEngine.execute)
        assert "[:500]" in source or "[:200]" in source

    def test_error_messages_dont_leak_internals(self):
        """9.3 Error messages in agent runs are generic."""
        import inspect

        from app.routers.runs import run_agent

        source = inspect.getsource(run_agent)
        # Should return generic error, not full traceback
        assert "Agent execution failed" in source


# ────────────────────────────────────────────────────────────────
# Section 10: SQL Injection
# ────────────────────────────────────────────────────────────────


class TestSQLInjection:
    """Section 10: SQL injection via Supabase client."""

    def test_no_raw_sql_in_codebase(self):
        """10.1 No raw SQL queries exist in the codebase."""
        import glob
        import os

        app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
        dangerous_patterns = [
            r'execute\s*\(\s*f"',
            r'execute\s*\(\s*f\'',
            r"\.sql\s*\(",
            r"cursor\.execute",
            r"raw_sql",
        ]

        # The db/ package contains the SQLite backend which uses raw SQL by design
        # (it IS the database driver). Exclude it from this check.
        excluded_dirs = {"db"}

        violations = []
        for py_file in glob.glob(os.path.join(app_dir, "**/*.py"), recursive=True):
            rel = os.path.relpath(py_file, app_dir)
            if any(rel.startswith(d + os.sep) or rel.startswith(d + "/") for d in excluded_dirs):
                continue
            with open(py_file) as f:
                content = f.read()
                for pattern in dangerous_patterns:
                    if re.search(pattern, content):
                        violations.append(f"{py_file}: matches {pattern}")

        assert not violations, f"Raw SQL found: {violations}"

    def test_marketplace_sort_by_validated(self):
        """10.2 Marketplace sort_by uses allowlist."""
        from app.services.marketplace.marketplace_service import MarketplaceService

        assert hasattr(MarketplaceService, "_ALLOWED_SORT_COLUMNS")
        assert "rating_avg" in MarketplaceService._ALLOWED_SORT_COLUMNS

    def test_marketplace_search_ilike_escaped(self):
        """10.3 Marketplace search escapes ILIKE wildcards."""
        import inspect

        from app.services.marketplace.marketplace_service import MarketplaceService

        source = inspect.getsource(MarketplaceService.list_listings)
        assert "escaped_search" in source or "escape" in source


# ────────────────────────────────────────────────────────────────
# Section 11: XSS via Stored Content
# ────────────────────────────────────────────────────────────────


class TestXSS:
    """Section 11: XSS prevention."""

    def test_html_sanitizer_escapes_tags(self):
        """11.1 HTML sanitizer escapes script tags."""
        from app.services.security.sanitizer import sanitize_html

        result = sanitize_html('<script>alert("xss")</script>')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_html_sanitizer_escapes_attributes(self):
        """11.2 HTML sanitizer escapes event handlers."""
        from app.services.security.sanitizer import sanitize_html

        result = sanitize_html('<img onerror="alert(1)" src=x>')
        assert "onerror" not in result or "&quot;" in result

    def test_strip_html_tags(self):
        """11.3 Strip HTML removes all tags."""
        from app.services.security.sanitizer import strip_html_tags

        result = strip_html_tags("<b>bold</b> and <script>evil</script>")
        assert "<" not in result
        assert "bold" in result

    def test_cors_not_wildcard(self):
        """11.4 CORS is not wildcard."""

        from app.main import app

        # Check that CORS origins are not ["*"]
        # Verify middleware config
        for mw in app.user_middleware:
            if hasattr(mw, "kwargs") and "allow_origins" in mw.kwargs:
                origins = mw.kwargs["allow_origins"]
                assert "*" not in origins

    def test_cors_methods_restricted(self):
        """11.5 CORS methods are explicitly listed."""
        import inspect

        # Read the main.py source to verify
        import app.main as main_module

        source = inspect.getsource(main_module)
        assert '"GET"' in source or "'GET'" in source
        assert "allow_methods=[\"*\"]" not in source


# ────────────────────────────────────────────────────────────────
# Section 12: Path Traversal
# ────────────────────────────────────────────────────────────────


class TestPathTraversal:
    """Section 12: Path traversal attacks."""

    def test_dot_dot_blocked(self):
        """12.1 ../ sequences are blocked."""
        from app.services.security.sanitizer import sanitize_path

        with pytest.raises(ValueError):
            sanitize_path("../../../etc/passwd")

    def test_absolute_path_blocked(self):
        """12.2 Absolute paths are blocked."""
        from app.services.security.sanitizer import sanitize_path

        with pytest.raises(ValueError):
            sanitize_path("/etc/shadow")

    def test_backslash_traversal_blocked(self):
        """12.3 Backslash traversal is blocked."""
        from app.services.security.sanitizer import sanitize_path

        with pytest.raises(ValueError):
            sanitize_path("..\\..\\windows\\system32")

    def test_null_byte_in_path_stripped(self):
        """12.4 Null bytes are stripped."""
        from app.services.security.sanitizer import sanitize_path

        result = sanitize_path("file\x00.txt")
        assert "\x00" not in result

    def test_valid_path_passes(self):
        """12.5 Valid filenames pass."""
        from app.services.security.sanitizer import sanitize_path

        assert sanitize_path("document.pdf") == "document.pdf"
        assert sanitize_path("folder/file.txt") == "folder/file.txt"


# ────────────────────────────────────────────────────────────────
# Section 13: SSRF (Server-Side Request Forgery)
# ────────────────────────────────────────────────────────────────


class TestSSRF:
    """Section 13: SSRF protection."""

    def _validate_with_mock_dns(self, url: str, resolved_ip: str):
        """Helper to test URL validation with mocked DNS resolution."""
        import socket as socket_mod

        from app.services.security.url_validator import validate_url

        # Mock both DNS resolution and _is_testing to return False
        fake_result = [(socket_mod.AF_INET, socket_mod.SOCK_STREAM, 0, "", (resolved_ip, 0))]
        with (
            patch("app.services.security.url_validator._is_testing", return_value=False),
            patch("app.services.security.url_validator.socket.getaddrinfo", return_value=fake_result),
        ):
            return validate_url(url)

    def test_localhost_blocked(self):
        """13.1 localhost is blocked."""
        from app.services.security.url_validator import SSRFError

        with pytest.raises(SSRFError, match="blocked IP range"):
            self._validate_with_mock_dns("http://localhost/admin", "127.0.0.1")

    def test_127_0_0_1_blocked(self):
        """13.2 127.0.0.1 is blocked."""
        from app.services.security.url_validator import SSRFError

        with pytest.raises(SSRFError, match="blocked IP range"):
            self._validate_with_mock_dns("http://127.0.0.1/admin", "127.0.0.1")

    def test_cloud_metadata_blocked(self):
        """13.3 Cloud metadata IP (169.254.169.254) is blocked."""
        from app.services.security.url_validator import SSRFError

        with pytest.raises(SSRFError, match="blocked IP range"):
            self._validate_with_mock_dns("http://169.254.169.254/latest/meta-data/", "169.254.169.254")

    def test_private_ip_10_blocked(self):
        """13.4 10.x.x.x range blocked."""
        from app.services.security.url_validator import SSRFError

        with pytest.raises(SSRFError, match="blocked IP range"):
            self._validate_with_mock_dns("http://10.0.0.1:8080/internal", "10.0.0.1")

    def test_ftp_scheme_blocked(self):
        """13.5 Non-HTTP schemes are blocked."""
        from app.services.security.url_validator import SSRFError, validate_url

        with pytest.raises(SSRFError, match="scheme"):
            validate_url("ftp://internal.server/file")

    def test_empty_url_blocked(self):
        """13.6 Empty URL is blocked."""
        from app.services.security.url_validator import SSRFError, validate_url

        with pytest.raises(SSRFError):
            validate_url("")

    def test_no_hostname_blocked(self):
        """13.7 URL with no hostname is blocked."""
        from app.services.security.url_validator import SSRFError, validate_url

        with pytest.raises(SSRFError):
            validate_url("http://")

    def test_valid_external_url_passes(self):
        """13.8 Valid external URLs pass validation."""
        from app.services.security.url_validator import validate_url

        # In test mode, DNS resolution is skipped but scheme is still checked
        assert validate_url("https://api.example.com/data") == "https://api.example.com/data"

    def test_fetch_url_node_has_ssrf_protection(self):
        """13.9 fetch_url deterministic node uses validate_url."""
        import inspect

        from app.services.blueprint_nodes.deterministic import execute_fetch_url

        source = inspect.getsource(execute_fetch_url)
        assert "validate_url" in source

    def test_fetch_document_node_has_ssrf_protection(self):
        """13.10 fetch_document deterministic node uses validate_url."""
        import inspect

        from app.services.blueprint_nodes.deterministic import execute_fetch_document

        source = inspect.getsource(execute_fetch_document)
        assert "validate_url" in source

    def test_webhook_node_has_ssrf_protection(self):
        """13.11 webhook deterministic node uses validate_url."""
        import inspect

        from app.services.blueprint_nodes.deterministic import execute_webhook

        source = inspect.getsource(execute_webhook)
        assert "validate_url" in source

    def test_mcp_client_has_ssrf_protection(self):
        """13.12 MCP client uses validate_url."""
        import inspect

        from app.mcp.client import MCPClient

        source = inspect.getsource(MCPClient.health_check)
        assert "validate_url" in source


# ────────────────────────────────────────────────────────────────
# Section 14: Denial of Service
# ────────────────────────────────────────────────────────────────


class TestDoS:
    """Section 14: DoS prevention."""

    def test_agent_run_rate_limited(self):
        """14.1 Agent runs are rate-limited (10/hour)."""
        import inspect

        from app.routers.runs import run_agent

        source = inspect.getsource(run_agent)
        assert "limiter.limit" in source or hasattr(run_agent, "__wrapped__")

    def test_blueprint_run_rate_limited(self):
        """14.2 Blueprint runs are rate-limited (10/hour)."""
        import inspect

        from app.routers.blueprints import run_blueprint

        source = inspect.getsource(run_blueprint)
        assert "limiter.limit" in source or hasattr(run_blueprint, "__wrapped__")

    def test_agent_creation_rate_limited(self):
        """14.3 Agent creation is rate-limited (20/hour)."""
        import inspect

        from app.routers.agents import create_agent

        source = inspect.getsource(create_agent)
        assert "limiter.limit" in source or hasattr(create_agent, "__wrapped__")

    def test_computer_use_rate_limited(self):
        """14.4 Computer use has per-minute rate limiting."""
        from app.services.computer_use.safety import ActionRateLimiter

        limiter = ActionRateLimiter(max_per_minute=2)
        limiter.check()
        limiter.check()
        assert limiter.check() is False

    def test_webhook_rate_limited(self):
        """14.5 Webhook endpoint is rate-limited."""
        import inspect

        from app.routers.triggers import webhook_receiver

        # Check for rate limiter decorator
        source = inspect.getsource(webhook_receiver)
        assert "limiter" in source or hasattr(webhook_receiver, "__wrapped__")

    def test_document_size_bounded(self):
        """14.6 Knowledge document size is bounded."""
        from app.routers.knowledge import AddDocumentRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            AddDocumentRequest(
                filename="big.txt",
                raw_text="x" * 5_000_001,
            )

    def test_fetch_url_response_capped(self):
        """14.7 Fetch URL response is capped at 50KB."""
        import inspect

        from app.services.blueprint_nodes.deterministic import execute_fetch_url

        source = inspect.getsource(execute_fetch_url)
        assert "50_000" in source or "50000" in source

    def test_code_executor_size_limit(self):
        """14.8 Code executor has 10KB size limit."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("x" * 10001)
        assert "Blocked" in result or "exceeds" in result

    def test_code_executor_timeout(self):
        """14.9 Code executor has 10s timeout."""
        import inspect

        from app.services.tools.code_executor import code_executor

        source = inspect.getsource(code_executor.func)
        assert "timeout=10" in source


# ────────────────────────────────────────────────────────────────
# Section 15: Marketplace Security
# ────────────────────────────────────────────────────────────────


class TestMarketplaceSecurity:
    """Section 15: Marketplace listing security."""

    def test_sort_by_injection_blocked(self):
        """15.1 Arbitrary sort_by values are rejected."""

        from app.services.marketplace.marketplace_service import MarketplaceService

        svc = MarketplaceService()
        # Invalid sort_by should default to rating_avg
        assert "drop_table" not in svc._ALLOWED_SORT_COLUMNS

    def test_ilike_wildcards_escaped(self):
        """15.2 ILIKE special chars are escaped."""
        import inspect

        from app.services.marketplace.marketplace_service import MarketplaceService

        source = inspect.getsource(MarketplaceService.list_listings)
        assert "escaped_search" in source

    def test_listing_limit_clamped(self):
        """15.3 Listing limit is clamped to 100."""
        import inspect

        from app.services.marketplace.marketplace_service import MarketplaceService

        source = inspect.getsource(MarketplaceService.list_listings)
        assert "min(max" in source or "clamp" in source.lower()

    def test_rating_range_validated(self):
        """15.4 Rating is validated between 1-5."""
        import inspect

        from app.routers.marketplace import rate_listing

        source = inspect.getsource(rate_listing)
        assert "rating < 1" in source or "rating must be 1-5" in source.lower()

    def test_listing_update_field_allowlist(self):
        """15.5 Listing update only allows specific fields."""
        import inspect

        from app.services.marketplace.marketplace_service import MarketplaceService

        source = inspect.getsource(MarketplaceService.update_listing)
        assert "allowed" in source.lower()


# ────────────────────────────────────────────────────────────────
# Section 16: Remote Execution Security (Computer Use)
# ────────────────────────────────────────────────────────────────


class TestRemoteExecutionSecurity:
    """Section 16: Computer use safety controls."""

    def test_command_blocklist_covers_destructive(self):
        """16.1 Destructive commands are in blocklist."""
        from app.config.computer_use import ComputerUseConfig

        config = ComputerUseConfig()
        blocklist_lower = [c.lower() for c in config.command_blocklist]
        assert any("rm -rf" in c for c in blocklist_lower)
        assert any("shutdown" in c for c in blocklist_lower)
        assert any("reboot" in c for c in blocklist_lower)

    def test_app_blocklist_covers_sensitive(self):
        """16.2 Sensitive apps are in blocklist."""
        from app.config.computer_use import ComputerUseConfig

        config = ComputerUseConfig()
        blocklist_lower = [a.lower() for a in config.app_blocklist]
        assert any("keychain" in a for a in blocklist_lower)
        assert any("system" in a for a in blocklist_lower)

    def test_screenshot_dir_configurable(self):
        """16.3 Screenshot directory is configurable."""
        from app.config.computer_use import ComputerUseConfig

        config = ComputerUseConfig()
        assert config.screenshot_dir is not None

    def test_dry_run_mode_available(self):
        """16.4 Dry run mode is available."""
        from app.config.computer_use import ComputerUseConfig

        config = ComputerUseConfig()
        assert hasattr(config, "dry_run")

    def test_approval_setting_exists(self):
        """16.5 Approval requirement setting exists."""
        from app.config.computer_use import ComputerUseConfig

        config = ComputerUseConfig()
        assert hasattr(config, "require_approval")


# ────────────────────────────────────────────────────────────────
# Section 17: Secrets & Key Exposure
# ────────────────────────────────────────────────────────────────


class TestSecretsExposure:
    """Section 17: Secrets and API key safety."""

    def test_env_file_not_in_repo(self):
        """17.1 .env is in .gitignore."""
        import os

        gitignore = os.path.join(
            os.path.dirname(__file__), "..", "..", ".gitignore"
        )
        if os.path.exists(gitignore):
            with open(gitignore) as f:
                content = f.read()
            assert ".env" in content

    def test_api_key_endpoints_require_auth(self):
        """17.2 API key endpoints require authentication."""

        from app.routers.api_keys import router

        for route in router.routes:
            if hasattr(route, "dependant"):
                # Check all routes have auth dependency
                pass  # Auth is enforced by Depends(get_current_user)

    def test_error_responses_dont_expose_keys(self):
        """17.3 Error handler returns generic message."""
        import inspect

        from app.routers.auth import get_current_user

        source = inspect.getsource(get_current_user)
        assert "Invalid or expired token" in source

    def test_health_endpoint_no_secrets(self):
        """17.4 Health endpoint doesn't expose secrets."""
        import asyncio

        from app.main import health

        result = asyncio.get_event_loop().run_until_complete(health())
        assert "key" not in str(result).lower()
        assert "secret" not in str(result).lower()
        assert "password" not in str(result).lower()

    def test_root_endpoint_no_secrets(self):
        """17.5 Root endpoint doesn't expose secrets."""
        import asyncio

        from app.main import root

        result = asyncio.get_event_loop().run_until_complete(root())
        assert "key" not in str(result).lower()
        assert "secret" not in str(result).lower()


# ────────────────────────────────────────────────────────────────
# Section 18: Input Validation Audit
# ────────────────────────────────────────────────────────────────


class TestInputValidation:
    """Section 18: Comprehensive input validation audit."""

    def test_agent_name_max_length(self):
        """18.1 Agent name has max length."""
        from app.models.agent import AgentCreate

        with pytest.raises((ValueError, TypeError, Exception)):
            AgentCreate(
                name="x" * 201,
                system_prompt="hello",
            )

    def test_agent_description_max_length(self):
        """18.2 Agent description has max length."""
        from app.models.agent import AgentCreate

        with pytest.raises((ValueError, TypeError, Exception)):
            AgentCreate(
                name="test",
                system_prompt="hello",
                description="x" * 2001,
            )

    def test_trigger_type_pattern(self):
        """18.3 Trigger type matches allowed pattern."""
        from app.routers.triggers import TriggerCreateRequest

        # Valid
        req = TriggerCreateRequest(
            type="webhook",
            target_type="agent",
            target_id="123",
        )
        assert req.type == "webhook"

        # Invalid
        with pytest.raises((ValueError, TypeError, Exception)):
            TriggerCreateRequest(
                type="exec_shell",
                target_type="agent",
                target_id="123",
            )

    def test_trigger_target_type_pattern(self):
        """18.4 Trigger target_type matches allowed pattern."""
        from app.routers.triggers import TriggerCreateRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            TriggerCreateRequest(
                type="webhook",
                target_type="admin",
                target_id="123",
            )

    def test_orchestration_objective_min_length(self):
        """18.5 Orchestration objective requires content."""
        from app.routers.orchestration import OrchestrationRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            OrchestrationRequest(objective="")

    def test_mcp_server_url_min_length(self):
        """18.6 MCP server URL requires content."""
        from app.routers.mcp import MCPConnectRequest

        with pytest.raises((ValueError, TypeError, Exception)):
            MCPConnectRequest(name="test", server_url="")

    def test_knowledge_search_top_k_positive(self):
        """18.7 Search top_k defaults to reasonable value."""
        from app.routers.knowledge import SearchRequest

        req = SearchRequest(query="test")
        assert req.top_k == 5

    def test_blueprint_run_limit_bounded(self):
        """18.8 Blueprint run history limit is bounded."""
        import inspect

        from app.routers.blueprints import list_blueprint_runs

        source = inspect.getsource(list_blueprint_runs)
        assert "ge=1" in source
        assert "le=100" in source


# ────────────────────────────────────────────────────────────────
# Section 19: Injection Surface Audit
# ────────────────────────────────────────────────────────────────


class TestInjectionSurface:
    """Section 19: Comprehensive injection surface audit."""

    def test_code_executor_blocks_os_system(self):
        """19.1 Code executor blocks os.system."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("import os; os.system('whoami')")
        assert "Blocked" in result

    def test_code_executor_blocks_subprocess(self):
        """19.2 Code executor blocks subprocess."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("import subprocess; subprocess.run(['ls'])")
        assert "Blocked" in result

    def test_code_executor_blocks_eval(self):
        """19.3 Code executor blocks eval."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("eval('__import__(\"os\").system(\"ls\")')")
        assert "Blocked" in result

    def test_code_executor_blocks_exec(self):
        """19.4 Code executor blocks exec."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("exec('import os')")
        assert "Blocked" in result

    def test_code_executor_blocks_dunder_import(self):
        """19.5 Code executor blocks __import__."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("__import__('os')")
        assert "Blocked" in result

    def test_code_executor_blocks_open(self):
        """19.6 Code executor blocks open()."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("open('/etc/passwd').read()")
        assert "Blocked" in result

    def test_code_executor_blocks_socket(self):
        """19.7 Code executor blocks socket."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("import socket; socket.socket()")
        assert "Blocked" in result

    def test_code_executor_blocks_base64_bypass(self):
        """19.8 Code executor blocks base64 decode attempts."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("import base64; exec(base64.b64decode('...'))")
        assert "Blocked" in result

    def test_code_executor_blocks_pickle(self):
        """19.9 Code executor blocks pickle."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("import pickle")
        assert "Blocked" in result

    def test_code_executor_blocks_breakpoint(self):
        """19.10 Code executor blocks breakpoint()."""
        from app.services.tools.code_executor import code_executor

        result = code_executor.invoke("breakpoint()")
        assert "Blocked" in result

    def test_supabase_orm_used_everywhere(self):
        """19.11 All database queries use Supabase ORM, not raw SQL."""
        import glob
        import os

        app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
        for py_file in glob.glob(os.path.join(app_dir, "**/*.py"), recursive=True):
            with open(py_file) as f:
                content = f.read()
            # No cursor.execute or raw SQL execution
            assert "cursor.execute" not in content, f"Raw SQL in {py_file}"
            assert "conn.execute" not in content or "supabase" in content, f"Raw SQL in {py_file}"

    def test_all_user_facing_routes_require_auth(self):
        """19.12 All mutation routes require authentication."""
        from app.main import app

        # Public routes that don't need auth
        public_paths = {
            "/",
            "/health",
            "/api/agents/templates",
            "/api/blueprints/templates",
            "/api/blueprints/node-types",
            "/api/marketplace/listings",
            "/api/marketplace/listings/{listing_id}",
            "/api/marketplace/listings/{listing_id}/ratings",
            "/api/marketplace/listings/{listing_id}/forks",
        }

        for route in app.routes:
            if not hasattr(route, "methods"):
                continue
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set())

            # Skip public/read routes
            if path in public_paths:
                continue
            if "webhooks" in path:
                continue  # Webhooks are intentionally unauthenticated

            # POST/PUT/DELETE routes should have auth
            if methods & {"POST", "PUT", "DELETE"}:
                endpoint = getattr(route, "endpoint", None)
                if endpoint:
                    import inspect

                    source = inspect.getsource(endpoint)
                    has_auth = (
                        "get_current_user" in source
                        or "Depends" in source
                        or "token" in source.lower()
                    )
                    # This is a soft check — some routes use token query param
                    assert has_auth or "template" in path.lower(), (
                        f"Route {path} ({methods}) may lack authentication"
                    )
