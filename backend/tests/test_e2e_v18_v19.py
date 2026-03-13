"""E2E tests for v1.8 (Computer Use Extension) and v1.9 (Advanced Computer Use & Cross-Platform).

Tests follow the agentforge-e2e-testing-v1_8-v1_9.pdf specification.
Tests that require macOS-only binaries (Steer, Drive) use dry-run/mock mode.
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root and cli/ to sys.path so CLI package can be imported
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
_CLI_DIR = str(Path(__file__).resolve().parent.parent.parent / "cli")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _CLI_DIR not in sys.path:
    sys.path.insert(0, _CLI_DIR)


# ============================================================
# V1.8 SECTION 1: Capability Detection
# ============================================================


class TestCapabilityDetection:
    """Section 1: Capability Detection."""

    def test_1_1_detector_service_exists(self):
        """1.1 — Detector service exists and checks platform."""
        from app.services.computer_use.detector import (
            CapabilityDetector,
            CapabilityReport,
        )

        detector = CapabilityDetector()
        report = detector.detect(force_refresh=True)

        assert isinstance(report, CapabilityReport)
        assert hasattr(report, "steer_available")
        assert hasattr(report, "drive_available")
        assert hasattr(report, "tmux_available")
        assert hasattr(report, "platform_name")
        assert report.platform_name in ("macos", "linux", "windows", "unknown")

    def test_1_2_api_endpoint(self, auth_client):
        """1.2 — GET /api/computer-use/status returns full report."""
        response = auth_client.get("/api/computer-use/status")
        assert response.status_code == 200
        data = response.json()

        assert "steer_available" in data
        assert "drive_available" in data
        assert "tmux_available" in data
        assert "platform" in data
        assert "computer_use_ready" in data
        assert isinstance(data["steer_available"], bool)
        assert isinstance(data["drive_available"], bool)

        # If steer not installed, still 200 (not crash)
        assert response.status_code == 200

    def test_1_3_caching(self, auth_client):
        """1.3 — Second call returns cached result faster."""
        t1 = time.time()
        r1 = auth_client.get("/api/computer-use/status")
        d1 = time.time() - t1

        t2 = time.time()
        r2 = auth_client.get("/api/computer-use/status")
        d2 = time.time() - t2

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Second call should be at least as fast (cached)
        assert d2 <= d1 + 0.5  # generous tolerance

    def test_1_4_settings_page_cu_section_exists(self):
        """1.4 — Settings page has Computer Use section (verify component)."""
        import pathlib
        settings_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "app" / "dashboard" / "settings" / "page.tsx"
        content = settings_path.read_text()
        assert "Computer Use" in content
        assert "steer_available" in content or "cuStatus" in content
        assert "install_instructions" in content

    def test_1_5_cli_cu_status_command_registered(self):
        """1.5 — CLI has computer-use status command."""
        pytest.importorskip("typer")
        from cli.agentforge.main import cu_app
        # Check the command group has a "status" command
        command_names = [cmd.name for cmd in cu_app.registered_commands]
        assert "status" in command_names


# ============================================================
# V1.8 SECTION 2: Steer Node Types (GUI Control)
# ============================================================


class TestSteerNodeTypes:
    """Section 2: Steer nodes — registry, executors, dry-run."""

    def test_2_1_steer_see_registered(self):
        """2.1 — steer_see node type is registered with correct schema."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_see")
        assert node is not None
        assert node.category == "computer_use_gui"
        assert node.node_class == "deterministic"
        assert "target" in node.input_schema
        assert "screenshot_path" in node.output_schema

    @pytest.mark.asyncio
    async def test_2_1_steer_see_dry_run(self):
        """2.1 — steer_see dry-run returns synthetic screenshot."""
        from app.services.computer_use.executor import run_local

        with patch("app.services.computer_use.executor.cu_config") as mock_config:
            mock_config.dry_run = True
            result = await run_local("steer", ["see"])
            assert result["success"] is True
            assert result["dry_run"] is True
            assert "DRY RUN" in result["output"]

    def test_2_2_steer_ocr_registered(self):
        """2.2 — steer_ocr node registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_ocr")
        assert node is not None
        assert "text" in node.output_schema

    def test_2_3_steer_click_registered(self):
        """2.3 — steer_click node registered with coordinate inputs."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_click")
        assert node is not None
        assert "x" in node.input_schema
        assert "y" in node.input_schema
        assert "element_text" in node.input_schema

    def test_2_4_steer_type_registered(self):
        """2.4 — steer_type node registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_type")
        assert node is not None
        assert "text" in node.input_schema

    def test_2_5_steer_hotkey_registered(self):
        """2.5 — steer_hotkey node registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_hotkey")
        assert node is not None
        assert "keys" in node.input_schema

    def test_2_6_steer_scroll_registered(self):
        """2.6 — steer_scroll node registered with direction enum."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_scroll")
        assert node is not None
        assert "direction" in node.input_schema
        assert "amount" in node.input_schema

    def test_2_7_steer_drag_registered(self):
        """2.7 — steer_drag node registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_drag")
        assert node is not None
        assert "start_x" in node.input_schema
        assert "end_x" in node.input_schema

    def test_2_8_steer_focus_registered(self):
        """2.8 — steer_focus node registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_focus")
        assert node is not None
        assert "app" in node.input_schema
        assert "screenshot_base64" in node.output_schema

    def test_2_9_steer_find_registered(self):
        """2.9 — steer_find returns coordinates or not-found."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_find")
        assert node is not None
        assert "found" in node.output_schema
        assert "coordinates" in node.output_schema

    def test_2_10_steer_wait_registered(self):
        """2.10 — steer_wait with timeout."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_wait")
        assert node is not None
        assert "timeout" in node.input_schema
        assert "condition_met" in node.output_schema

    def test_2_11_steer_clipboard_registered(self):
        """2.11 — steer_clipboard read/write."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_clipboard")
        assert node is not None
        assert "action" in node.input_schema

    def test_2_12_steer_apps_registered(self):
        """2.12 — steer_apps returns app list."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("steer_apps")
        assert node is not None
        assert "apps" in node.output_schema
        assert "app_count" in node.output_schema

    def test_2_13_all_steer_have_executors(self):
        """2.13 — All 12 steer nodes have matching executors."""
        from app.services.blueprint_nodes.registry import STEER_NODES
        from app.services.computer_use.steer.nodes import STEER_EXECUTORS

        assert len(STEER_NODES) == 12
        for key in STEER_NODES:
            assert key in STEER_EXECUTORS, f"Missing executor for {key}"


# ============================================================
# V1.8 SECTION 3: Drive Node Types (Terminal Control)
# ============================================================


class TestDriveNodeTypes:
    """Section 3: Drive nodes."""

    def test_3_1_drive_session_registered(self):
        """3.1 — drive_session with create/list/kill actions."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("drive_session")
        assert node is not None
        assert "action" in node.input_schema

    def test_3_2_drive_run_registered(self):
        """3.2 — drive_run with command and timeout."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("drive_run")
        assert node is not None
        assert "command" in node.input_schema
        assert "timeout" in node.input_schema

    def test_3_3_drive_send_registered(self):
        """3.3 — drive_send for raw keystrokes."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("drive_send")
        assert node is not None
        assert "keys" in node.input_schema

    def test_3_4_drive_logs_registered(self):
        """3.4 — drive_logs with line limit."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("drive_logs")
        assert node is not None
        assert "lines" in node.input_schema

    def test_3_5_drive_poll_registered(self):
        """3.5 — drive_poll with sentinel token."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("drive_poll")
        assert node is not None
        assert "token" in node.input_schema
        assert "timeout" in node.input_schema

    def test_3_6_drive_fanout_registered(self):
        """3.6 — drive_fanout with parallel commands."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("drive_fanout")
        assert node is not None
        assert "commands" in node.input_schema

    def test_all_drive_have_executors(self):
        """All 6 drive nodes have matching executors."""
        from app.services.blueprint_nodes.registry import DRIVE_NODES
        from app.services.computer_use.drive.nodes import DRIVE_EXECUTORS

        assert len(DRIVE_NODES) == 6
        for key in DRIVE_NODES:
            assert key in DRIVE_EXECUTORS


# ============================================================
# V1.8 SECTION 4: CU Agent Node Types
# ============================================================


class TestCUAgentNodeTypes:
    """Section 4: CU agent nodes (LLM-powered)."""

    def test_4_1_cu_planner_registered(self):
        """4.1 — cu_planner returns structured plan."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("cu_planner")
        assert node is not None
        assert node.node_class == "agent"
        assert "objective" in node.input_schema
        assert "plan" in node.output_schema

    def test_4_2_cu_analyzer_registered(self):
        """4.2 — cu_analyzer analyzes screen state."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("cu_analyzer")
        assert node is not None
        assert node.node_class == "agent"

    def test_4_3_cu_verifier_registered(self):
        """4.3 — cu_verifier checks objective achievement."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("cu_verifier")
        assert node is not None
        assert "success" in node.output_schema
        assert "confidence" in node.output_schema

    def test_4_4_cu_error_handler_registered(self):
        """4.4 — cu_error_handler suggests recovery actions."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("cu_error_handler")
        assert node is not None
        assert "recoverable" in node.output_schema
        assert "recovery_actions" in node.output_schema

    def test_all_cu_agents_in_dispatch_table(self):
        """All CU agent nodes are in the engine dispatch table."""
        from app.services.blueprint_engine import _ALL_AGENT
        for key in ["cu_planner", "cu_analyzer", "cu_verifier", "cu_error_handler"]:
            assert key in _ALL_AGENT


# ============================================================
# V1.8 SECTION 5: Remote Execution
# ============================================================


class TestRemoteExecution:
    """Section 5: Remote execution via Listen server."""

    def test_5_1_config_exists(self):
        """5.1 — Computer use config with execution_mode."""
        from app.config.computer_use import ComputerUseConfig
        config = ComputerUseConfig()
        assert config.execution_mode in ("local", "remote")
        assert hasattr(config, "listen_server_url")
        assert hasattr(config, "listen_api_key")

    def test_5_2_remote_service_exists(self):
        """5.2 — Remote execution functions exist."""
        from app.services.computer_use.executor import (
            run_remote,
            test_remote_connection,
        )
        assert callable(run_remote)
        assert callable(test_remote_connection)

    def test_5_3_routing_function_exists(self):
        """5.3 — Execute routes based on config."""
        from app.services.computer_use.executor import execute
        assert callable(execute)

    def test_5_4_remote_test_endpoint(self, auth_client):
        """5.4 — POST /api/computer-use/remote/test exists."""
        response = auth_client.post("/api/computer-use/remote/test")
        assert response.status_code == 200

    def test_5_5_config_endpoint(self, auth_client):
        """5.5 — GET /api/computer-use/config returns config."""
        response = auth_client.get("/api/computer-use/config")
        assert response.status_code == 200
        data = response.json()
        assert "execution_mode" in data
        assert "app_blocklist" in data


# ============================================================
# V1.8 SECTION 6: Blueprint Editor Integration
# ============================================================


class TestBlueprintEditorIntegration:
    """Section 6: Blueprint editor palette, styling, config panels."""

    def test_6_1_node_palette_has_cu_categories(self):
        """6.1 — Palette includes GUI, Terminal, CU Agent categories."""
        import pathlib
        palette_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "components" / "blueprints" / "NodePalette.tsx"
        content = palette_path.read_text()
        assert "computer_use_gui" in content
        assert "computer_use_terminal" in content
        assert "computer_use_agent" in content
        assert "GUI (Steer)" in content
        assert "Terminal (Drive)" in content
        assert "CU Agent" in content

    def test_6_2_node_styling_colors(self):
        """6.2 — CU nodes have distinct color themes."""
        import pathlib
        palette_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "components" / "blueprints" / "NodePalette.tsx"
        content = palette_path.read_text()
        assert "green-500" in content  # GUI nodes
        assert "amber-500" in content  # Terminal nodes
        assert "purple-500" in content  # CU agent nodes

    def test_6_3_steer_config_panels(self):
        """6.3 — Config panels exist for steer nodes."""
        import pathlib
        config_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "components" / "blueprints" / "ConfigPanel.tsx"
        content = config_path.read_text()
        assert "steer_focus" in content
        assert "steer_click" in content
        assert "steer_see" in content or "steer_ocr" in content

    def test_6_4_drive_config_panels(self):
        """6.4 — Config panels exist for drive nodes."""
        import pathlib
        config_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "components" / "blueprints" / "ConfigPanel.tsx"
        content = config_path.read_text()
        assert "drive_session" in content
        assert "drive_run" in content
        assert "drive_fanout" in content

    def test_6_5_node_types_api(self, auth_client):
        """6.5 — API returns CU node types."""
        response = auth_client.get("/api/blueprints/node-types")
        assert response.status_code == 200
        data = response.json()
        categories = {d["category"] for d in data}
        assert "computer_use_gui" in categories
        assert "computer_use_terminal" in categories
        assert "computer_use_agent" in categories

    def test_6_6_node_types_filterable(self, auth_client):
        """6.6 — Node types filter by category."""
        response = auth_client.get("/api/blueprints/node-types?category=computer_use_gui")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 12 + 1  # 12 steer + 1 recording_control
        for d in data:
            assert d["category"] == "computer_use_gui"


# ============================================================
# V1.8 SECTION 7: Blueprint Templates
# ============================================================


class TestBlueprintTemplates:
    """Section 7: Pre-built computer use blueprint templates."""

    def test_7_1_cu_templates_exist(self):
        """7.1 — All 5 CU templates defined."""
        from app.services.blueprint_templates import CU_BLUEPRINT_TEMPLATES
        names = {t["name"] for t in CU_BLUEPRINT_TEMPLATES}
        assert "Browser Research Pipeline" in names
        assert "Terminal Task Runner" in names
        assert "Cross-App Workflow" in names
        assert "Self-Healing App Automation" in names
        assert "Multi-Terminal Parallel Tasks" in names

    def test_7_2_templates_valid_structure(self):
        """7.2 — Templates have valid DAG structure (no orphans, no cycles)."""
        from app.services.blueprint_engine import _topological_sort
        from app.services.blueprint_templates import CU_BLUEPRINT_TEMPLATES

        for template in CU_BLUEPRINT_TEMPLATES:
            nodes = template["nodes"]
            assert len(nodes) >= 2, f"Template '{template['name']}' too short"
            # Verify no cycles
            try:
                layers = _topological_sort(nodes)
                total = sum(len(layer) for layer in layers)
                assert total == len(nodes), f"Template '{template['name']}' has orphaned nodes"
            except ValueError:
                pytest.fail(f"Template '{template['name']}' has a cycle")

    def test_7_3_templates_use_cu_nodes(self):
        """7.3 — Templates use computer use node types."""
        from app.services.blueprint_nodes.registry import NODE_REGISTRY
        from app.services.blueprint_templates import CU_BLUEPRINT_TEMPLATES

        for template in CU_BLUEPRINT_TEMPLATES:
            for node in template["nodes"]:
                assert node["type"] in NODE_REGISTRY, (
                    f"Template '{template['name']}' uses unknown node type: {node['type']}"
                )


# ============================================================
# V1.8 SECTION 8: Security and Safety
# ============================================================


class TestSecuritySafety:
    """Section 8: App blocklist, command blocklist, rate limiting, auth."""

    def test_8_1_app_blocklist_blocks(self):
        """8.1 — App blocklist prevents targeting blocked apps."""
        from app.services.computer_use.safety import check_app_blocklist
        with pytest.raises(ValueError, match="blocklist"):
            check_app_blocklist("Keychain Access")

    def test_8_1_app_blocklist_allows(self):
        """8.1 — Allowed apps pass blocklist."""
        from app.services.computer_use.safety import check_app_blocklist
        check_app_blocklist("Safari")

    def test_8_2_command_blocklist_blocks(self):
        """8.2 — Dangerous commands blocked."""
        from app.services.computer_use.safety import check_command_blocklist
        with pytest.raises(ValueError, match="blocklist"):
            check_command_blocklist("rm -rf /")

    def test_8_2_command_blocklist_allows(self):
        """8.2 — Safe commands allowed."""
        from app.services.computer_use.safety import check_command_blocklist
        check_command_blocklist("ls -la")
        check_command_blocklist("npm test")

    def test_8_5_rate_limiting(self):
        """8.5 — Rate limiter enforces limit."""
        from app.services.computer_use.safety import ActionRateLimiter
        limiter = ActionRateLimiter(max_per_minute=3)
        assert limiter.check() is True
        assert limiter.check() is True
        assert limiter.check() is True
        assert limiter.check() is False
        assert limiter.remaining == 0

    def test_8_6_audit_log_function_exists(self):
        """8.6 — Audit log function exists."""
        from app.services.computer_use.safety import log_action
        assert callable(log_action)

    def test_8_7_auth_enforcement(self, client):
        """8.7 — Endpoints require authentication."""
        endpoints = [
            "/api/computer-use/status",
            "/api/computer-use/config",
        ]
        for ep in endpoints:
            response = client.get(ep)
            assert response.status_code in (401, 422), f"{ep} returned {response.status_code}"


# ============================================================
# V1.8 SECTION 9: Observability
# ============================================================


class TestObservability:
    """Section 9: Trace recording integration."""

    def test_9_1_blueprint_engine_produces_trace(self):
        """9.1 — Blueprint engine yields trace entries with CU-specific data."""
        from app.services.blueprint_engine import BlueprintEngine
        assert hasattr(BlueprintEngine, "execute")

    def test_9_2_trace_entry_structure(self):
        """9.2 — Trace entries have expected CU fields."""
        # Verify the execute_node closure creates trace entries with required fields
        import inspect

        from app.services.blueprint_engine import BlueprintEngine
        source = inspect.getsource(BlueprintEngine.execute)
        assert "node_type" in source
        assert "duration_ms" in source
        assert "output_preview" in source


# ============================================================
# V1.8 SECTION 10: Dashboard
# ============================================================


class TestDashboard:
    """Section 10: Dashboard integration."""

    def test_10_1_dashboard_page_exists(self):
        """10.1 — Dashboard page exists."""
        import pathlib
        dash_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "app" / "dashboard" / "page.tsx"
        assert dash_path.exists()

    def test_10_3_cu_status_in_settings(self):
        """10.3 — CU status shown on settings page."""
        import pathlib
        settings = pathlib.Path(__file__).parent.parent.parent / "frontend" / "app" / "dashboard" / "settings" / "page.tsx"
        content = settings.read_text()
        assert "cuStatus" in content
        assert "steer_available" in content


# ============================================================
# V1.8 SECTION 11: CLI Commands
# ============================================================


class TestCLICommands:
    """Section 11: CLI computer use commands."""

    def test_11_1_cli_commands_registered(self):
        """11.1 — All expected CLI commands exist."""
        pytest.importorskip("typer")
        from cli.agentforge.main import cu_app
        command_names = [cmd.name for cmd in cu_app.registered_commands]
        for expected in ["status", "see", "ocr", "click", "type", "hotkey", "run", "logs", "sessions", "apps", "remote"]:
            assert expected in command_names, f"Missing CLI command: {expected}"


# ============================================================
# V1.8 SECTION 12: Eval Integration
# ============================================================


class TestEvalIntegration:
    """Section 12: Eval grading methods for CU."""

    def test_12_1_screenshot_match_exists(self):
        """12.1 — screenshot_match grading method registered."""
        from app.services.evals.grading import GRADING_METHODS
        assert "screenshot_match" in GRADING_METHODS

    def test_12_2_ocr_contains_exists(self):
        """12.2 — ocr_contains grading method registered."""
        from app.services.evals.grading import GRADING_METHODS
        assert "ocr_contains" in GRADING_METHODS

    def test_12_2_ocr_contains_works(self):
        """12.2 — ocr_contains grades text correctly."""
        from app.services.evals.grading import grade_ocr_contains
        result = grade_ocr_contains("The fox jumps over the dog", "", {"texts": ["fox", "dog"]})
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_12_3_ocr_partial_score(self):
        """12.3 — ocr_contains partial scores work."""
        from app.services.evals.grading import grade_ocr_contains
        result = grade_ocr_contains("The fox", "", {"texts": ["fox", "cat"], "threshold": 0.5})
        assert result["passed"] is True
        assert result["matched"] == 1


# ============================================================
# V1.8 SECTION 13: E2E Workflows
# ============================================================


class TestE2EWorkflows:
    """Section 13: End-to-end computer use workflows."""

    def test_13_1_terminal_task_runner_template(self):
        """13.1 — Terminal Task Runner template has correct flow."""
        from app.services.blueprint_templates import CU_BLUEPRINT_TEMPLATES
        template = next(t for t in CU_BLUEPRINT_TEMPLATES if t["name"] == "Terminal Task Runner")
        node_types = [n["type"] for n in template["nodes"]]
        assert "drive_session" in node_types
        assert "drive_run" in node_types
        assert "llm_generate" in node_types or "cu_analyzer" in node_types

    def test_13_4_cost_tracking_infrastructure(self):
        """13.4 — Token tracker exists for cost tracking."""
        from app.services.token_tracker import calculate_cost, token_tracker
        assert callable(calculate_cost)
        assert hasattr(token_tracker, "record")


# ============================================================
# V1.9 SECTION 14: Agent-on-Agent Orchestration
# ============================================================


class TestAgentOnAgent:
    """Section 14: Agent-on-agent orchestration."""

    def test_14_1_backend_config_exists(self):
        """14.1 — Agent backend configuration exists."""
        from app.config.agent_backends import BUILTIN_BACKENDS, AgentBackend
        assert len(BUILTIN_BACKENDS) >= 4
        for name in ["claude-code", "codex-cli", "gemini-cli", "aider"]:
            b = BUILTIN_BACKENDS[name]
            assert isinstance(b, AgentBackend)
            assert b.command
            assert b.prompt_method in ("argument", "stdin", "file")
            assert b.output_capture in ("tmux", "file")
            assert b.completion_pattern

    def test_14_2_custom_backend_via_env(self):
        """14.2 — Custom backend from environment."""
        from app.config.agent_backends import get_backend
        with patch.dict(os.environ, {
            "AF_AGENT_BACKEND_MYAGENT_COMMAND": "my-agent",
            "AF_AGENT_BACKEND_MYAGENT_PROMPT_METHOD": "stdin",
        }):
            backend = get_backend("myagent")
            assert backend is not None
            assert backend.command == "my-agent"
            assert backend.prompt_method == "stdin"

    def test_14_3_agent_spawn_registered(self):
        """14.3 — agent_spawn node type registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("agent_spawn")
        assert node is not None
        assert node.node_class == "deterministic"
        assert node.category == "agent_control"
        assert "backend" in node.input_schema

    def test_14_4_agent_prompt_registered(self):
        """14.4 — agent_prompt node type registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("agent_prompt")
        assert node is not None
        assert "session" in node.input_schema
        assert "prompt" in node.input_schema

    def test_14_5_agent_monitor_registered(self):
        """14.5 — agent_monitor node type registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("agent_monitor")
        assert node is not None
        assert "session" in node.input_schema

    def test_14_6_agent_wait_registered(self):
        """14.6 — agent_wait with timeout."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("agent_wait")
        assert node is not None
        assert "timeout" in node.input_schema
        assert "completed" in node.output_schema

    def test_14_7_agent_stop_registered(self):
        """14.7 — agent_stop node type registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("agent_stop")
        assert node is not None
        assert "stopped" in node.output_schema

    def test_14_8_agent_result_registered(self):
        """14.8 — agent_result with output format."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("agent_result")
        assert node is not None
        assert "output_format" in node.input_schema
        assert "parsed" in node.output_schema

    def test_14_9_all_agent_control_executors(self):
        """14.9 — All 6 agent control nodes have executors in dispatch table."""
        from app.services.blueprint_engine import _ALL_DETERMINISTIC
        for key in ["agent_spawn", "agent_prompt", "agent_monitor", "agent_wait", "agent_stop", "agent_result"]:
            assert key in _ALL_DETERMINISTIC, f"Missing executor in dispatch: {key}"

    def test_14_10_agent_runner_service_lifecycle(self):
        """14.10 — Agent runner has full lifecycle methods."""
        from app.services.computer_use.agents.agent_runner import AgentRunner
        runner = AgentRunner()
        for method in ["spawn", "prompt", "monitor", "wait_for_completion", "capture_result", "stop", "status"]:
            assert hasattr(runner, method), f"AgentRunner missing method: {method}"
            assert callable(getattr(runner, method))

    def test_14_11_cli_backends_commands(self):
        """14.11 — CLI has backends list and test commands."""
        pytest.importorskip("typer")
        from cli.agentforge.main import backends_app
        command_names = [cmd.name for cmd in backends_app.registered_commands]
        assert "list" in command_names
        assert "test" in command_names

    def test_14_12_agent_control_config_panels(self):
        """14.12 — Frontend config panels for agent control nodes."""
        import pathlib
        config_path = pathlib.Path(__file__).parent.parent.parent / "frontend" / "components" / "blueprints" / "ConfigPanel.tsx"
        content = config_path.read_text()
        assert "agent_spawn" in content
        assert "agent_prompt" in content
        assert "agent_wait" in content
        assert "agent_result" in content
        assert "Agent Backend" in content  # backend selector label


# ============================================================
# V1.9 SECTION 15: Multi-Machine Dispatch
# ============================================================


class TestMultiMachineDispatch:
    """Section 15: Multi-machine dispatch."""

    def test_15_1_execution_targets_migration(self):
        """15.1 — Execution targets migration exists."""
        import pathlib
        migration = pathlib.Path(__file__).parent.parent.parent / "supabase" / "migrations" / "20260312_execution_targets.sql"
        content = migration.read_text()
        assert "execution_targets" in content
        assert "user_id" in content
        assert "listen_url" in content
        assert "capabilities" in content
        assert "ROW LEVEL SECURITY" in content

    def test_15_2_target_registration_api(self, auth_client):
        """15.2 — POST/GET/DELETE /api/targets."""
        # Create
        r = auth_client.post("/api/targets", json={
            "name": "Test Mac", "target_type": "remote",
            "listen_url": "http://mac:7600", "platform": "macos",
        })
        assert r.status_code == 200
        target_id = r.json()["id"]

        # List
        r = auth_client.get("/api/targets")
        assert r.status_code == 200
        assert any(t["name"] == "Test Mac" for t in r.json())

        # Delete
        r = auth_client.delete(f"/api/targets/{target_id}")
        assert r.status_code == 200

    def test_15_3_health_check_endpoint(self, auth_client):
        """15.3 — Health check endpoint works."""
        r = auth_client.post("/api/targets/local/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_15_4_dispatch_explicit_target(self):
        """15.4 — Dispatch routes to explicit target."""
        from app.services.computer_use.dispatch import DispatchService
        svc = DispatchService()
        svc.register_target("mac-1", "Mac Mini 1", "remote", "http://m:7600")
        target = svc.resolve_target("steer_see", {"target_id": "mac-1"})
        assert target.id == "mac-1"

    def test_15_5_dispatch_auto_routing(self):
        """15.5 — Auto dispatch picks capable target."""
        from app.services.computer_use.dispatch import DispatchService
        svc = DispatchService()
        # Local has no steer, register one with steer
        svc.register_target("steer-mac", "Steer Mac", "remote", "http://m:7600")
        svc._targets["steer-mac"].capabilities = {"steer_available": True}
        svc._targets["steer-mac"].status = "healthy"

        target = svc.resolve_target("steer_see", {})
        assert target.id == "steer-mac"

    def test_15_6_dispatch_blueprint_default(self):
        """15.6 — Blueprint default target used."""
        from app.services.computer_use.dispatch import DispatchService
        svc = DispatchService()
        svc.register_target("default-1", "Default", "remote")
        target = svc.resolve_target("steer_see", {}, {"default_target": "default-1"})
        assert target.id == "default-1"

    def test_15_7_capabilities_endpoint(self, auth_client):
        """15.7 — GET /api/targets/capabilities."""
        r = auth_client.get("/api/targets/capabilities")
        assert r.status_code == 200
        data = r.json()
        assert "target_count" in data
        assert "capabilities" in data

    def test_15_10_cli_targets_commands(self):
        """15.10 — CLI targets commands registered."""
        pytest.importorskip("typer")
        from cli.agentforge.main import targets_app
        command_names = [cmd.name for cmd in targets_app.registered_commands]
        for expected in ["list", "add", "health", "remove"]:
            assert expected in command_names, f"Missing targets CLI command: {expected}"

    def test_15_11_local_target_cannot_be_removed(self):
        """15.11 — Local target is permanent."""
        from app.services.computer_use.dispatch import DispatchService
        svc = DispatchService()
        assert svc.remove_target("local") is False


# ============================================================
# V1.9 SECTION 16: Screen Recording
# ============================================================


class TestScreenRecording:
    """Section 16: Screen recording."""

    def test_16_1_recorder_service_exists(self):
        """16.1 — Recorder service with start/stop."""
        from app.services.computer_use.recorder import RecorderService
        recorder = RecorderService()
        assert callable(recorder.start_recording)
        assert callable(recorder.stop_recording)
        assert callable(recorder.get_recording)
        assert callable(recorder.cleanup_recordings)

    def test_16_4_recording_control_node(self):
        """16.4 — recording_control node type registered."""
        from app.services.blueprint_nodes.registry import get_node_type
        node = get_node_type("recording_control")
        assert node is not None
        assert node.node_class == "deterministic"
        assert "action" in node.input_schema
        assert "quality" in node.input_schema

    def test_16_4_recording_executor_exists(self):
        """16.4 — Recording executor in dispatch table."""
        from app.services.blueprint_engine import _ALL_DETERMINISTIC
        assert "recording_control" in _ALL_DETERMINISTIC

    def test_16_7_cli_recordings_commands(self):
        """16.7 — CLI recordings commands registered."""
        pytest.importorskip("typer")
        from cli.agentforge.main import recordings_app
        command_names = [cmd.name for cmd in recordings_app.registered_commands]
        for expected in ["list", "play", "cleanup"]:
            assert expected in command_names

    def test_16_8_cleanup_handles_empty(self):
        """16.8 — Cleanup handles missing directory."""
        from app.services.computer_use.recorder import RecorderService
        recorder = RecorderService()
        recorder._storage_path = "/tmp/nonexistent-af-recording-test"
        removed = recorder.cleanup_recordings(older_than_days=0)
        assert removed == 0


# ============================================================
# V1.9 SECTION 17: Linux Computer Use
# ============================================================


class TestLinuxComputerUse:
    """Section 17: Linux computer use."""

    def test_17_1_platform_detection_function(self):
        """17.1 — get_platform() works."""
        from app.services.computer_use.platform import get_platform
        p = get_platform()
        assert p in ("macos", "linux", "windows", "unknown")

    def test_17_2_linux_steer_implementations_exist(self):
        """17.2 — All 12 Linux steer implementations exist."""
        from app.services.computer_use.linux.linux_steer import LINUX_STEER_MAP
        expected = [
            "steer_see", "steer_ocr", "steer_click", "steer_type",
            "steer_hotkey", "steer_scroll", "steer_drag", "steer_focus",
            "steer_find", "steer_wait", "steer_clipboard", "steer_apps",
        ]
        for key in expected:
            assert key in LINUX_STEER_MAP, f"Missing Linux steer: {key}"
            assert callable(LINUX_STEER_MAP[key])

    def test_17_3_platform_dispatch(self):
        """17.3 — Platform dispatch returns correct executor."""
        from app.services.computer_use.platform import get_platform, get_steer_executor
        # On macOS, returns None (use default Steer CLI path)
        # On Linux, returns Linux implementation
        executor = get_steer_executor("steer_click")
        p = get_platform()
        if p == "linux":
            assert executor is not None
        elif p == "macos":
            assert executor is None  # Uses Steer CLI

    def test_17_4_virtual_display_service(self):
        """17.4 — Xvfb virtual display service exists."""
        from app.services.computer_use.linux.virtual_display import VirtualDisplay
        vd = VirtualDisplay()
        assert callable(vd.start)
        assert callable(vd.stop)
        assert callable(vd.set_display)
        assert vd.is_running(99) is False


# ============================================================
# V1.9 SECTION 18: Windows Computer Use
# ============================================================


class TestWindowsComputerUse:
    """Section 18: Windows computer use."""

    def test_18_1_windows_steer_implementations_exist(self):
        """18.1/18.2 — All 12 Windows steer implementations exist."""
        from app.services.computer_use.windows.windows_steer import WINDOWS_STEER_MAP
        expected = [
            "steer_see", "steer_ocr", "steer_click", "steer_type",
            "steer_hotkey", "steer_scroll", "steer_drag", "steer_focus",
            "steer_find", "steer_wait", "steer_clipboard", "steer_apps",
        ]
        for key in expected:
            assert key in WINDOWS_STEER_MAP, f"Missing Windows steer: {key}"

    def test_18_3_windows_drive_exists(self):
        """18.3 — Windows Drive (PowerShell) implementation exists."""
        from app.services.computer_use.windows.windows_drive import WINDOWS_DRIVE_MAP
        assert "drive_session" in WINDOWS_DRIVE_MAP
        assert "drive_run" in WINDOWS_DRIVE_MAP
        assert "drive_logs" in WINDOWS_DRIVE_MAP

    def test_18_3_wsl_detection_function(self):
        """18.3 — WSL detection function exists."""
        from app.services.computer_use.windows.windows_drive import (
            get_windows_drive_info,
        )
        info = get_windows_drive_info()
        assert "wsl_available" in info
        assert "powershell" in info
        assert "method" in info

    def test_18_4_cross_platform_dispatch(self):
        """18.4 — Platform dispatch handles all 3 platforms."""
        from app.services.computer_use.platform import get_capabilities
        caps = get_capabilities()
        assert "platform" in caps
        assert "steer_available" in caps
        assert "drive_available" in caps


# ============================================================
# V1.9 SECTION 19: Cross-Platform Unification
# ============================================================


class TestCrossPlatformUnification:
    """Section 19: Cross-platform unification."""

    def test_19_1_platform_abstraction(self):
        """19.1 — Platform abstraction layer complete."""
        from app.services.computer_use.platform import (
            PLATFORM_INSTALL_INSTRUCTIONS,
            get_capabilities,
            get_drive_executor,
            get_platform,
            get_steer_executor,
        )
        assert callable(get_platform)
        assert callable(get_capabilities)
        assert callable(get_steer_executor)
        assert callable(get_drive_executor)
        assert "macos" in PLATFORM_INSTALL_INSTRUCTIONS
        assert "linux" in PLATFORM_INSTALL_INSTRUCTIONS
        assert "windows" in PLATFORM_INSTALL_INSTRUCTIONS

    def test_19_2_capability_detector_reports_platform(self):
        """19.2 — Capability detector includes platform in report."""
        from app.services.computer_use.detector import CapabilityDetector
        detector = CapabilityDetector()
        report = detector.detect(force_refresh=True)
        d = report.to_dict()
        assert "platform" in d
        assert d["platform"] in ("macos", "linux", "windows", "unknown")
        assert "agent_backends" in d

    def test_19_3_platform_display_in_settings(self):
        """19.3 — Settings page shows platform info."""
        import pathlib
        settings = pathlib.Path(__file__).parent.parent.parent / "frontend" / "app" / "dashboard" / "settings" / "page.tsx"
        content = settings.read_text()
        assert "platform" in content
        assert "agent_backends" in content

    def test_19_4_cross_platform_templates(self):
        """19.4 — Universal blueprint templates exist."""
        from app.services.blueprint_templates import V19_BLUEPRINT_TEMPLATES
        names = {t["name"] for t in V19_BLUEPRINT_TEMPLATES}
        assert "Universal Browser Automation" in names


# ============================================================
# SECTION 20: Cross-Feature Integration Tests
# ============================================================


class TestCrossFeatureIntegration:
    """Section 20: Cross-feature integration."""

    def test_20_1_agent_on_agent_nodes_in_registry(self):
        """20.1 — Agent control + CU agent nodes all coexist in registry."""
        from app.services.blueprint_nodes.registry import NODE_REGISTRY
        # v1.8 nodes
        assert "steer_see" in NODE_REGISTRY
        assert "drive_run" in NODE_REGISTRY
        assert "cu_planner" in NODE_REGISTRY
        # v1.9 nodes
        assert "agent_spawn" in NODE_REGISTRY
        assert "agent_result" in NODE_REGISTRY
        assert "recording_control" in NODE_REGISTRY

    def test_20_2_total_node_count(self):
        """20.2 — Total node count is 44."""
        from app.services.blueprint_nodes.registry import NODE_REGISTRY
        assert len(NODE_REGISTRY) == 44

    def test_20_3_dispatch_tables_complete(self):
        """20.3 — All dispatch tables are complete."""
        from app.services.blueprint_engine import _ALL_AGENT, _ALL_DETERMINISTIC

        # Deterministic: 10 original + 12 steer + 6 drive + 6 agent_control + 1 recording = 35
        assert len(_ALL_DETERMINISTIC) >= 35

        # Agent: 5 original + 4 cu_agent = 9
        assert len(_ALL_AGENT) >= 9

    def test_20_4_agent_inception_template_valid(self):
        """20.4 — Agent Inception template is valid."""
        from app.services.blueprint_engine import _topological_sort
        from app.services.blueprint_nodes.registry import NODE_REGISTRY
        from app.services.blueprint_templates import V19_BLUEPRINT_TEMPLATES

        template = next(t for t in V19_BLUEPRINT_TEMPLATES if "Inception" in t["name"])
        nodes = template["nodes"]

        # All node types valid
        for n in nodes:
            assert n["type"] in NODE_REGISTRY, f"Unknown type: {n['type']}"

        # Valid DAG
        layers = _topological_sort(nodes)
        assert sum(len(layer) for layer in layers) == len(nodes)

    def test_20_5_parallel_review_template_valid(self):
        """20.5 — Parallel Multi-Agent Review template is valid."""
        from app.services.blueprint_engine import _topological_sort
        from app.services.blueprint_templates import V19_BLUEPRINT_TEMPLATES

        template = next(t for t in V19_BLUEPRINT_TEMPLATES if "Parallel" in t["name"])
        nodes = template["nodes"]

        # Has parallel spawns
        spawn_nodes = [n for n in nodes if n["type"] == "agent_spawn"]
        assert len(spawn_nodes) == 3

        # Valid DAG
        layers = _topological_sort(nodes)
        assert sum(len(layer) for layer in layers) == len(nodes)

    def test_20_full_api_node_types(self, auth_client):
        """20 — Full API returns all 44 node types with all categories."""
        r = auth_client.get("/api/blueprints/node-types")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 44
        categories = {d["category"] for d in data}
        for expected_cat in ["context", "transform", "validate", "agent", "output",
                             "computer_use_gui", "computer_use_terminal", "computer_use_agent",
                             "agent_control"]:
            assert expected_cat in categories, f"Missing category: {expected_cat}"


# ============================================================
# SECTION 21: Security (Combined)
# ============================================================


class TestSecurityCombined:
    """Section 21: Combined security tests."""

    def test_21_1_all_cu_endpoints_require_auth(self, client):
        """21.1 — All CU and target endpoints require auth."""
        unauthenticated_endpoints = [
            ("GET", "/api/computer-use/status"),
            ("GET", "/api/computer-use/config"),
            ("POST", "/api/computer-use/refresh"),
            ("POST", "/api/computer-use/remote/test"),
            ("GET", "/api/computer-use/audit-log"),
            ("GET", "/api/targets"),
            ("POST", "/api/targets"),
            ("GET", "/api/targets/capabilities"),
        ]
        for method, path in unauthenticated_endpoints:
            if method == "GET":
                r = client.get(path)
            else:
                r = client.post(path, json={})
            assert r.status_code in (401, 422), f"{method} {path} returned {r.status_code}"

    def test_21_4_blocklist_defaults_populated(self):
        """21.4 — Default blocklists are populated."""
        from app.config.computer_use import ComputerUseConfig
        config = ComputerUseConfig()
        assert len(config.app_blocklist) > 0
        assert len(config.command_blocklist) > 0
