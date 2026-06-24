"""Computer use configuration."""

import os
from dataclasses import dataclass


@dataclass
class ComputerUseConfig:
    """Configuration for computer use features.

    Env vars are read in ``__post_init__`` (not as class-level defaults) so the
    config reflects the environment at *instantiation* time and can be rebuilt —
    class-level ``os.getenv(...)`` defaults are frozen once at import.
    """

    # "local" = steer/drive on same machine, "remote" = dispatch to Listen server
    execution_mode: str = None  # type: ignore[assignment]

    # Remote Listen server settings
    listen_server_url: str = None  # type: ignore[assignment]
    listen_api_key: str = None  # type: ignore[assignment]

    # Safety settings
    require_approval: bool = None  # type: ignore[assignment]
    max_actions_per_minute: int = None  # type: ignore[assignment]

    # Blocklists
    app_blocklist: list[str] = None  # type: ignore[assignment]
    command_blocklist: list[str] = None  # type: ignore[assignment]

    # Screenshot settings. Default to a per-user dir, not world-readable /tmp —
    # screenshots can capture sensitive on-screen content.
    screenshot_dir: str = None  # type: ignore[assignment]
    redact_screenshots: bool = None  # type: ignore[assignment]

    # Dry-run mode for testing
    dry_run: bool = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.execution_mode is None:
            self.execution_mode = os.getenv("CU_EXECUTION_MODE", "local")
        if self.listen_server_url is None:
            self.listen_server_url = os.getenv("CU_LISTEN_URL", "")
        if self.listen_api_key is None:
            self.listen_api_key = os.getenv("CU_LISTEN_API_KEY", "")
        if self.require_approval is None:
            self.require_approval = os.getenv("CU_REQUIRE_APPROVAL", "false").lower() == "true"
        if self.max_actions_per_minute is None:
            self.max_actions_per_minute = int(os.getenv("CU_MAX_ACTIONS_PER_MINUTE", "30"))
        if self.screenshot_dir is None:
            self.screenshot_dir = os.getenv(
                "CU_SCREENSHOT_DIR", os.path.expanduser("~/.forge/screenshots")
            )
        if self.redact_screenshots is None:
            self.redact_screenshots = os.getenv("CU_REDACT_SCREENSHOTS", "false").lower() == "true"
        if self.dry_run is None:
            self.dry_run = os.getenv("CU_DRY_RUN", "false").lower() == "true"

        if self.app_blocklist is None:
            default_blocklist = os.getenv(
                "CU_APP_BLOCKLIST",
                "System Preferences,System Settings,Keychain Access",
            )
            self.app_blocklist = [a.strip() for a in default_blocklist.split(",") if a.strip()]

        if self.command_blocklist is None:
            default_blocklist = os.getenv(
                "CU_COMMAND_BLOCKLIST",
                "rm -rf /,shutdown,reboot,halt,poweroff",
            )
            self.command_blocklist = [c.strip() for c in default_blocklist.split(",") if c.strip()]


cu_config = ComputerUseConfig()
