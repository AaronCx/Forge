"""Computer use configuration."""

import os
from dataclasses import dataclass


@dataclass
class ComputerUseConfig:
    """Configuration for computer use features."""

    # "local" = steer/drive on same machine, "remote" = dispatch to Listen server
    execution_mode: str = os.getenv("CU_EXECUTION_MODE", "local")

    # Remote Listen server settings
    listen_server_url: str = os.getenv("CU_LISTEN_URL", "")
    listen_api_key: str = os.getenv("CU_LISTEN_API_KEY", "")

    # Safety settings
    require_approval: bool = os.getenv("CU_REQUIRE_APPROVAL", "false").lower() == "true"
    max_actions_per_minute: int = int(os.getenv("CU_MAX_ACTIONS_PER_MINUTE", "30"))

    # Blocklists
    app_blocklist: list[str] = None  # type: ignore[assignment]
    command_blocklist: list[str] = None  # type: ignore[assignment]

    # Screenshot settings
    screenshot_dir: str = os.getenv("CU_SCREENSHOT_DIR", "/tmp/agentforge-screenshots")
    redact_screenshots: bool = os.getenv("CU_REDACT_SCREENSHOTS", "false").lower() == "true"

    # Dry-run mode for testing
    dry_run: bool = os.getenv("CU_DRY_RUN", "false").lower() == "true"

    def __post_init__(self):
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
