"""Tests for computer use features — capability detection, node types, safety, and API."""

import os
from unittest.mock import patch

import pytest

# ============================================================
# Capability Detection
# ============================================================


def test_capability_detector_returns_report():
    """Detector returns a CapabilityReport with expected fields."""
    from app.services.computer_use.detector import CapabilityDetector

    detector = CapabilityDetector()
    report = detector.detect()

    assert hasattr(report, "steer_available")
    assert hasattr(report, "drive_available")
    assert hasattr(report, "tmux_available")
    assert hasattr(report, "is_macos")
    assert hasattr(report, "missing")
    assert isinstance(report.missing, list)


def test_capability_detector_caches():
    """Detector caches results."""
    from app.services.computer_use.detector import CapabilityDetector

    detector = CapabilityDetector()
    r1 = detector.detect()
    r2 = detector.detect()
    assert r1 is r2  # Same object — cached


def test_capability_detector_invalidate():
    """Detector cache can be invalidated."""
    from app.services.computer_use.detector import CapabilityDetector

    detector = CapabilityDetector()
    r1 = detector.detect()
    detector.invalidate_cache()
    r2 = detector.detect()
    assert r1 is not r2  # Different object — re-detected


def test_capability_report_to_dict():
    """CapabilityReport.to_dict() returns expected structure."""
    from app.services.computer_use.detector import CapabilityReport

    report = CapabilityReport(steer_available=True, drive_available=False)
    d = report.to_dict()
    assert d["steer_available"] is True
    assert d["drive_available"] is False
    assert d["computer_use_ready"] is False  # drive missing
    assert "missing" in d
    assert "platform" in d
    assert "agent_backends" in d


def test_capability_report_platform_field():
    """CapabilityReport includes platform name."""
    from app.services.computer_use.detector import CapabilityReport

    report = CapabilityReport(platform_name="linux")
    d = report.to_dict()
    assert d["platform"] == "linux"


def test_capability_detector_agent_backends():
    """Detector discovers available agent backends."""
    from app.services.computer_use.detector import CapabilityDetector

    detector = CapabilityDetector()
    report = detector.detect(force_refresh=True)
    assert isinstance(report.agent_backends, list)


# ============================================================
# Configuration
# ============================================================


def test_config_defaults():
    """Computer use config has sensible defaults."""
    from app.config.computer_use import ComputerUseConfig

    config = ComputerUseConfig()
    assert config.execution_mode == "local"
    assert config.max_actions_per_minute == 30
    assert isinstance(config.app_blocklist, list)
    assert isinstance(config.command_blocklist, list)
    assert config.dry_run is False


def test_config_blocklists():
    """Default blocklists include known dangerous entries."""
    from app.config.computer_use import ComputerUseConfig

    config = ComputerUseConfig()
    assert "System Preferences" in config.app_blocklist or "System Settings" in config.app_blocklist
    assert "Keychain Access" in config.app_blocklist
    assert any("rm -rf" in cmd for cmd in config.command_blocklist)


# ============================================================
# Safety
# ============================================================


def test_app_blocklist_blocks():
    """App blocklist raises on blocked apps."""
    from app.services.computer_use.safety import check_app_blocklist

    with pytest.raises(ValueError, match="blocklist"):
        check_app_blocklist("Keychain Access")


def test_app_blocklist_allows():
    """App blocklist allows non-blocked apps."""
    from app.services.computer_use.safety import check_app_blocklist

    check_app_blocklist("Safari")  # Should not raise


def test_command_blocklist_blocks():
    """Command blocklist raises on dangerous commands."""
    from app.services.computer_use.safety import check_command_blocklist

    with pytest.raises(ValueError, match="blocklist"):
        check_command_blocklist("rm -rf /")


def test_command_blocklist_allows():
    """Command blocklist allows safe commands."""
    from app.services.computer_use.safety import check_command_blocklist

    check_command_blocklist("ls -la")  # Should not raise
    check_command_blocklist("npm test")  # Should not raise


def test_rate_limiter():
    """Rate limiter tracks and limits actions."""
    from app.services.computer_use.safety import ActionRateLimiter

    limiter = ActionRateLimiter(max_per_minute=3)
    assert limiter.check() is True
    assert limiter.check() is True
    assert limiter.check() is True
    assert limiter.check() is False  # Exceeded
    assert limiter.remaining == 0


# ============================================================
# Node Registry
# ============================================================


def test_steer_nodes_registered():
    """All 12 Steer node types are registered."""
    from app.services.blueprint_nodes.registry import STEER_NODES

    expected = [
        "steer_see", "steer_ocr", "steer_click", "steer_type",
        "steer_hotkey", "steer_scroll", "steer_drag", "steer_focus",
        "steer_find", "steer_wait", "steer_clipboard", "steer_apps",
    ]
    for key in expected:
        assert key in STEER_NODES, f"Missing steer node: {key}"
    assert len(STEER_NODES) == 12


def test_drive_nodes_registered():
    """All 6 Drive node types are registered."""
    from app.services.blueprint_nodes.registry import DRIVE_NODES

    expected = ["drive_session", "drive_run", "drive_send", "drive_logs", "drive_poll", "drive_fanout"]
    for key in expected:
        assert key in DRIVE_NODES, f"Missing drive node: {key}"
    assert len(DRIVE_NODES) == 6


def test_cu_agent_nodes_registered():
    """All 4 CU agent node types are registered."""
    from app.services.blueprint_nodes.registry import CU_AGENT_NODES

    expected = ["cu_planner", "cu_analyzer", "cu_verifier", "cu_error_handler"]
    for key in expected:
        assert key in CU_AGENT_NODES, f"Missing cu_agent node: {key}"
    assert len(CU_AGENT_NODES) == 4


def test_steer_nodes_are_deterministic():
    """Steer nodes are classified as deterministic."""
    from app.services.blueprint_nodes.registry import STEER_NODES

    for node in STEER_NODES.values():
        assert node.node_class == "deterministic"
        assert node.category == "computer_use_gui"


def test_drive_nodes_are_deterministic():
    """Drive nodes are classified as deterministic."""
    from app.services.blueprint_nodes.registry import DRIVE_NODES

    for node in DRIVE_NODES.values():
        assert node.node_class == "deterministic"
        assert node.category == "computer_use_terminal"


def test_cu_agent_nodes_are_agent():
    """CU agent nodes are classified as agent."""
    from app.services.blueprint_nodes.registry import CU_AGENT_NODES

    for node in CU_AGENT_NODES.values():
        assert node.node_class == "agent"
        assert node.category == "computer_use_agent"


# ============================================================
# Executor Dispatch Tables
# ============================================================


def test_steer_executors_match_nodes():
    """Every Steer node type has a corresponding executor."""
    from app.services.blueprint_nodes.registry import STEER_NODES
    from app.services.computer_use.steer.nodes import STEER_EXECUTORS

    for key in STEER_NODES:
        assert key in STEER_EXECUTORS, f"Missing executor for {key}"


def test_drive_executors_match_nodes():
    """Every Drive node type has a corresponding executor."""
    from app.services.blueprint_nodes.registry import DRIVE_NODES
    from app.services.computer_use.drive.nodes import DRIVE_EXECUTORS

    for key in DRIVE_NODES:
        assert key in DRIVE_EXECUTORS, f"Missing executor for {key}"


def test_cu_agent_executors_match_nodes():
    """Every CU agent node type has a corresponding executor."""
    from app.services.blueprint_nodes.registry import CU_AGENT_NODES
    from app.services.computer_use.agent_nodes import CU_AGENT_EXECUTORS

    for key in CU_AGENT_NODES:
        assert key in CU_AGENT_EXECUTORS, f"Missing executor for {key}"


# ============================================================
# Blueprint Engine Integration
# ============================================================


def test_blueprint_engine_knows_cu_nodes():
    """Blueprint engine's merged dispatch tables include CU executors."""
    from app.services.blueprint_engine import _ALL_AGENT, _ALL_DETERMINISTIC

    assert "steer_see" in _ALL_DETERMINISTIC
    assert "drive_run" in _ALL_DETERMINISTIC
    assert "cu_planner" in _ALL_AGENT
    assert "cu_verifier" in _ALL_AGENT


# ============================================================
# Executor (dry-run mode)
# ============================================================


@pytest.mark.asyncio
async def test_executor_dry_run():
    """Executor dry-run mode returns synthetic output."""
    from app.services.computer_use.executor import run_local

    with patch("app.services.computer_use.executor.cu_config") as mock_config:
        mock_config.dry_run = True
        result = await run_local("steer", ["see"])
        assert result["success"] is True
        assert result["dry_run"] is True
        assert "DRY RUN" in result["output"]


# ============================================================
# Eval Grading Methods
# ============================================================


def test_screenshot_match_grading_exists():
    """screenshot_match grading method is registered."""
    from app.services.evals.grading import GRADING_METHODS

    assert "screenshot_match" in GRADING_METHODS


def test_ocr_contains_grading_exists():
    """ocr_contains grading method is registered."""
    from app.services.evals.grading import GRADING_METHODS

    assert "ocr_contains" in GRADING_METHODS


def test_ocr_contains_basic():
    """ocr_contains works with text content directly."""
    from app.services.evals.grading import grade_ocr_contains

    result = grade_ocr_contains(
        "The quick brown fox jumps over the lazy dog",
        "",
        {"texts": ["fox", "dog"]},
    )
    assert result["passed"] is True
    assert result["score"] == 1.0


def test_ocr_contains_partial():
    """ocr_contains returns partial scores."""
    from app.services.evals.grading import grade_ocr_contains

    result = grade_ocr_contains(
        "The quick brown fox",
        "",
        {"texts": ["fox", "cat"], "threshold": 0.5},
    )
    assert result["passed"] is True
    assert result["matched"] == 1
    assert result["total"] == 2


# ============================================================
# API Endpoints
# ============================================================


def test_computer_use_status_endpoint(auth_client):
    """GET /api/computer-use/status returns capability report."""
    response = auth_client.get("/api/computer-use/status")
    assert response.status_code == 200
    data = response.json()
    assert "steer_available" in data
    assert "drive_available" in data
    assert "tmux_available" in data
    assert "computer_use_ready" in data


def test_computer_use_config_endpoint(auth_client):
    """GET /api/computer-use/config returns configuration."""
    response = auth_client.get("/api/computer-use/config")
    assert response.status_code == 200
    data = response.json()
    assert "execution_mode" in data
    assert "app_blocklist" in data
    assert "command_blocklist" in data
    assert "rate_limit_remaining" in data


def test_computer_use_refresh_endpoint(auth_client):
    """POST /api/computer-use/refresh clears cache and re-detects."""
    response = auth_client.post("/api/computer-use/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "steer_available" in data


def test_computer_use_requires_auth(client):
    """Computer use endpoints require authentication."""
    response = client.get("/api/computer-use/status")
    assert response.status_code in (401, 422)  # 401 or 422 depending on auth middleware


# ============================================================
# Blueprint Templates
# ============================================================


def test_cu_blueprint_templates_exist():
    """Computer use blueprint templates are defined."""
    from app.services.blueprint_templates import CU_BLUEPRINT_TEMPLATES

    assert len(CU_BLUEPRINT_TEMPLATES) == 5

    names = {t["name"] for t in CU_BLUEPRINT_TEMPLATES}
    assert "Browser Research Pipeline" in names
    assert "Terminal Task Runner" in names
    assert "Cross-App Workflow" in names
    assert "Self-Healing App Automation" in names
    assert "Multi-Terminal Parallel Tasks" in names


def test_cu_templates_use_cu_nodes():
    """CU blueprint templates use computer use node types."""
    from app.services.blueprint_templates import CU_BLUEPRINT_TEMPLATES

    all_types = set()
    for template in CU_BLUEPRINT_TEMPLATES:
        for node in template["nodes"]:
            all_types.add(node["type"])

    assert "steer_focus" in all_types
    assert "steer_ocr" in all_types
    assert "drive_run" in all_types
    assert "drive_session" in all_types
    assert "cu_planner" in all_types
    assert "cu_verifier" in all_types


# ============================================================
# CLI Command Registration
# ============================================================


def test_cli_cu_commands():
    """CLI computer-use command group is registered with subcommands."""
    if not os.path.exists(str(__import__("pathlib").Path(__file__).parent.parent / ".venv" / "bin" / "forge")):
        pytest.skip("forge CLI not installed")

    import pathlib
    import subprocess

    agentforge = str(pathlib.Path(__file__).parent.parent / ".venv" / "bin" / "forge")
    cli_dir = str(pathlib.Path(__file__).parent.parent.parent / "cli")
    env = {**os.environ, "PYTHONPATH": cli_dir}

    result = subprocess.run(
        [agentforge, "computer-use", "--help"],  # variable name kept for clarity
        capture_output=True, text=True, timeout=10, env=env,
    )
    assert result.returncode == 0
    output = result.stdout.lower()
    assert "status" in output
    assert "see" in output
    assert "ocr" in output
    assert "click" in output
    assert "run" in output
    assert "sessions" in output
    assert "apps" in output
    assert "remote" in output


# ============================================================
# v1.9: Agent Backends Configuration
# ============================================================


def test_builtin_backends():
    """Pre-configured agent backends are defined."""
    from app.config.agent_backends import BUILTIN_BACKENDS

    assert "claude-code" in BUILTIN_BACKENDS
    assert "codex-cli" in BUILTIN_BACKENDS
    assert "gemini-cli" in BUILTIN_BACKENDS
    assert "aider" in BUILTIN_BACKENDS


def test_backend_lookup():
    """Can look up backends by name."""
    from app.config.agent_backends import get_backend

    backend = get_backend("claude-code")
    assert backend is not None
    assert backend.command == "claude"
    assert backend.prompt_method == "argument"


def test_backend_list():
    """Can list all backends."""
    from app.config.agent_backends import list_backends

    backends = list_backends()
    assert len(backends) >= 4
    names = {b["name"] for b in backends}
    assert "claude-code" in names


def test_unknown_backend_returns_none():
    """Unknown backend returns None."""
    from app.config.agent_backends import get_backend

    assert get_backend("nonexistent-agent") is None


# ============================================================
# v1.9: Agent Control Node Types
# ============================================================


def test_agent_control_nodes_registered():
    """All 6 agent control node types are registered."""
    from app.services.blueprint_nodes.registry import AGENT_CONTROL_NODES

    expected = ["agent_spawn", "agent_prompt", "agent_monitor", "agent_wait", "agent_stop", "agent_result"]
    for key in expected:
        assert key in AGENT_CONTROL_NODES, f"Missing agent control node: {key}"
    assert len(AGENT_CONTROL_NODES) == 6


def test_agent_control_nodes_are_deterministic():
    """Agent control nodes are classified as deterministic."""
    from app.services.blueprint_nodes.registry import AGENT_CONTROL_NODES

    for node in AGENT_CONTROL_NODES.values():
        assert node.node_class == "deterministic"
        assert node.category == "agent_control"


def test_agent_control_executors_match_nodes():
    """Every agent control node type has a corresponding executor."""
    from app.services.blueprint_nodes.registry import AGENT_CONTROL_NODES
    from app.services.computer_use.agents.nodes import AGENT_CONTROL_EXECUTORS

    for key in AGENT_CONTROL_NODES:
        assert key in AGENT_CONTROL_EXECUTORS, f"Missing executor for {key}"


def test_blueprint_engine_knows_agent_control_nodes():
    """Blueprint engine's dispatch tables include agent control executors."""
    from app.services.blueprint_engine import _ALL_DETERMINISTIC

    assert "agent_spawn" in _ALL_DETERMINISTIC
    assert "agent_prompt" in _ALL_DETERMINISTIC
    assert "agent_wait" in _ALL_DETERMINISTIC
    assert "agent_result" in _ALL_DETERMINISTIC


# ============================================================
# v1.9: Recording Control
# ============================================================


def test_recording_control_node_registered():
    """recording_control node type is registered."""
    from app.services.blueprint_nodes.registry import RECORDING_NODES

    assert "recording_control" in RECORDING_NODES
    assert RECORDING_NODES["recording_control"].node_class == "deterministic"


def test_recording_executor_registered():
    """Recording executor is in the dispatch table."""
    from app.services.computer_use.recorder import RECORDING_EXECUTORS

    assert "recording_control" in RECORDING_EXECUTORS


def test_blueprint_engine_knows_recording_node():
    """Blueprint engine includes recording executor."""
    from app.services.blueprint_engine import _ALL_DETERMINISTIC

    assert "recording_control" in _ALL_DETERMINISTIC


def test_recorder_service_cleanup():
    """Recorder cleanup handles empty directory."""
    from app.services.computer_use.recorder import RecorderService

    recorder = RecorderService()
    removed = recorder.cleanup_recordings(older_than_days=0)
    assert isinstance(removed, int)


# ============================================================
# v1.9: Multi-Machine Dispatch
# ============================================================


def test_dispatch_service_local_target():
    """Dispatch service always has local target."""
    from app.services.computer_use.dispatch import DispatchService

    service = DispatchService()
    targets = service.list_targets()
    assert len(targets) >= 1
    assert any(t["id"] == "local" for t in targets)


def test_dispatch_register_target():
    """Can register and remove execution targets."""
    from app.services.computer_use.dispatch import DispatchService

    service = DispatchService()
    target = service.register_target(
        target_id="test-1",
        name="Test Server",
        target_type="remote",
        listen_url="http://test:7600",
        platform="linux",
    )
    assert target.name == "Test Server"
    assert target.platform == "linux"

    targets = service.list_targets()
    assert len(targets) == 2

    assert service.remove_target("test-1") is True
    assert service.remove_target("local") is False  # Can't remove local


def test_dispatch_resolve_fallback():
    """Dispatch resolves to local target by default."""
    from app.services.computer_use.dispatch import DispatchService

    service = DispatchService()
    target = service.resolve_target("steer_see", {})
    assert target.id == "local"


def test_dispatch_resolve_explicit_target():
    """Dispatch uses explicit target_id from node config."""
    from app.services.computer_use.dispatch import DispatchService

    service = DispatchService()
    service.register_target("remote-1", "Remote Mac", "remote", "http://r:7600")
    target = service.resolve_target("steer_see", {"target_id": "remote-1"})
    assert target.id == "remote-1"


# ============================================================
# v1.9: Cross-Platform
# ============================================================


def test_platform_detection():
    """Platform layer detects current platform."""
    from app.services.computer_use.platform import get_platform

    p = get_platform()
    assert p in ("macos", "linux", "windows", "unknown")


def test_platform_capabilities():
    """Platform layer returns capabilities."""
    from app.services.computer_use.platform import get_capabilities

    caps = get_capabilities()
    assert "platform" in caps
    assert "steer_available" in caps
    assert "drive_available" in caps
    assert "tmux_available" in caps


def test_platform_install_instructions():
    """Platform install instructions are defined for all platforms."""
    from app.services.computer_use.platform import PLATFORM_INSTALL_INSTRUCTIONS

    assert "macos" in PLATFORM_INSTALL_INSTRUCTIONS
    assert "linux" in PLATFORM_INSTALL_INSTRUCTIONS
    assert "windows" in PLATFORM_INSTALL_INSTRUCTIONS


def test_linux_steer_map():
    """Linux steer map has all 12 node implementations."""
    from app.services.computer_use.linux.linux_steer import LINUX_STEER_MAP

    assert len(LINUX_STEER_MAP) == 12
    assert "steer_see" in LINUX_STEER_MAP
    assert "steer_click" in LINUX_STEER_MAP
    assert "steer_ocr" in LINUX_STEER_MAP
    assert "steer_apps" in LINUX_STEER_MAP


def test_windows_steer_map():
    """Windows steer map has all 12 node implementations."""
    from app.services.computer_use.windows.windows_steer import WINDOWS_STEER_MAP

    assert len(WINDOWS_STEER_MAP) == 12
    assert "steer_see" in WINDOWS_STEER_MAP
    assert "steer_click" in WINDOWS_STEER_MAP


def test_windows_drive_map():
    """Windows drive map has key commands."""
    from app.services.computer_use.windows.windows_drive import WINDOWS_DRIVE_MAP

    assert "drive_session" in WINDOWS_DRIVE_MAP
    assert "drive_run" in WINDOWS_DRIVE_MAP
    assert "drive_logs" in WINDOWS_DRIVE_MAP


def test_virtual_display_init():
    """Virtual display service initializes."""
    from app.services.computer_use.linux.virtual_display import VirtualDisplay

    vd = VirtualDisplay()
    assert vd.is_running(99) is False


# ============================================================
# v1.9: Blueprint Templates
# ============================================================


def test_v19_blueprint_templates_exist():
    """v1.9 blueprint templates are defined."""
    from app.services.blueprint_templates import V19_BLUEPRINT_TEMPLATES

    assert len(V19_BLUEPRINT_TEMPLATES) == 3

    names = {t["name"] for t in V19_BLUEPRINT_TEMPLATES}
    assert "Agent Inception — Claude Code Review" in names
    assert "Parallel Multi-Agent Code Review" in names
    assert "Universal Browser Automation" in names


def test_v19_templates_use_agent_control_nodes():
    """v1.9 templates use agent control node types."""
    from app.services.blueprint_templates import V19_BLUEPRINT_TEMPLATES

    all_types = set()
    for template in V19_BLUEPRINT_TEMPLATES:
        for node in template["nodes"]:
            all_types.add(node["type"])

    assert "agent_spawn" in all_types
    assert "agent_prompt" in all_types
    assert "agent_wait" in all_types
    assert "agent_result" in all_types


# ============================================================
# v1.9: API Endpoints — Targets
# ============================================================


def test_targets_list_endpoint(auth_client):
    """GET /api/targets returns target list."""
    response = auth_client.get("/api/targets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # At least local target


def test_targets_create_endpoint(auth_client):
    """POST /api/targets creates a new target."""
    response = auth_client.post("/api/targets", json={
        "name": "Test Server",
        "target_type": "remote",
        "listen_url": "http://test:7600",
        "platform": "linux",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Server"


def test_targets_capabilities_endpoint(auth_client):
    """GET /api/targets/capabilities returns aggregated capabilities."""
    response = auth_client.get("/api/targets/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "target_count" in data
    assert "capabilities" in data
