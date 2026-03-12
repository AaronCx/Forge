"""Multi-machine dispatch — route blueprint nodes to different execution targets."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.computer_use.executor import execute, test_remote_connection

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTarget:
    """A machine that can run computer use commands."""

    id: str
    name: str
    target_type: str  # "local" or "remote"
    listen_url: str = ""
    api_key: str = ""
    platform: str = "macos"  # "macos", "linux", "windows"
    capabilities: dict[str, Any] = field(default_factory=dict)
    status: str = "unknown"  # "healthy", "unhealthy", "unknown"
    last_health_check: str = ""


class DispatchService:
    """Manages execution targets and routes nodes to the correct machine."""

    def __init__(self) -> None:
        self._targets: dict[str, ExecutionTarget] = {}
        # Always register local as default
        self._targets["local"] = ExecutionTarget(
            id="local",
            name="Local Machine",
            target_type="local",
            status="healthy",
        )

    def register_target(
        self,
        target_id: str,
        name: str,
        target_type: str = "remote",
        listen_url: str = "",
        api_key: str = "",
        platform: str = "macos",
    ) -> ExecutionTarget:
        """Register a new execution target."""
        target = ExecutionTarget(
            id=target_id,
            name=name,
            target_type=target_type,
            listen_url=listen_url,
            api_key=api_key,
            platform=platform,
        )
        self._targets[target_id] = target
        return target

    def remove_target(self, target_id: str) -> bool:
        """Remove an execution target."""
        if target_id == "local":
            return False  # Can't remove local
        return self._targets.pop(target_id, None) is not None

    def list_targets(self) -> list[dict[str, Any]]:
        """List all targets with current status."""
        return [
            {
                "id": t.id,
                "name": t.name,
                "type": t.target_type,
                "platform": t.platform,
                "listen_url": t.listen_url,
                "capabilities": t.capabilities,
                "status": t.status,
                "last_health_check": t.last_health_check,
            }
            for t in self._targets.values()
        ]

    def get_target(self, target_id: str) -> ExecutionTarget | None:
        """Get a specific target."""
        return self._targets.get(target_id)

    async def health_check(self, target_id: str) -> dict[str, Any]:
        """Run a health check on a target."""
        target = self._targets.get(target_id)
        if not target:
            return {"error": f"Unknown target: {target_id}"}

        if target.target_type == "local":
            from app.services.computer_use.detector import capability_detector
            report = capability_detector.detect()
            target.capabilities = report.to_dict()
            target.status = "healthy"
            target.platform = "macos" if report.is_macos else "linux"
        else:
            try:
                result = await test_remote_connection()
                target.status = "healthy" if result.get("connected") else "unhealthy"
                target.capabilities = result.get("capabilities", {})
            except Exception as e:
                target.status = "unhealthy"
                logger.warning("Health check failed for %s: %s", target_id, e)

        import datetime
        target.last_health_check = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return {
            "id": target.id,
            "status": target.status,
            "capabilities": target.capabilities,
            "platform": target.platform,
        }

    async def health_check_all(self) -> list[dict[str, Any]]:
        """Run health checks on all targets."""
        results = []
        for target_id in self._targets:
            result = await self.health_check(target_id)
            results.append(result)
        return results

    def resolve_target(
        self,
        node_type_key: str,
        node_config: dict[str, Any],
        blueprint_config: dict[str, Any] | None = None,
    ) -> ExecutionTarget:
        """Determine which target should execute a given node."""
        # 1. Explicit target_id in node config
        explicit = node_config.get("target_id")
        if explicit and explicit in self._targets:
            return self._targets[explicit]

        # 2. Blueprint default target
        if blueprint_config:
            default_target = blueprint_config.get("default_target")
            if default_target and default_target in self._targets:
                return self._targets[default_target]

        # 3. Capability-based routing
        requires_gui = node_type_key.startswith("steer_")
        requires_terminal = node_type_key.startswith("drive_") or node_type_key.startswith("agent_")

        for target in self._targets.values():
            if target.status != "healthy":
                continue
            caps = target.capabilities
            if requires_gui and caps.get("steer_available"):
                return target
            if requires_terminal and caps.get("drive_available") or caps.get("tmux_available"):
                return target

        # 4. Fall back to local
        return self._targets["local"]


dispatch_service = DispatchService()
