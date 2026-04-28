"""Configuration loader for Forge CLI."""

import os
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib


CONFIG_DIR = Path.home() / ".forge"
CONFIG_FILE = CONFIG_DIR / "config.toml"

_config: dict | None = None


def get_config() -> dict:
    """Load config from ~/.forge/config.toml or env vars."""
    global _config
    if _config is not None:
        return _config

    config = {
        "api_url": os.environ.get("FORGE_API_URL", "http://localhost:8000"),
        "api_key": os.environ.get("FORGE_API_KEY", ""),
        "default_model": "",
    }

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "rb") as f:
            file_config = tomllib.load(f)
            # Support both flat and nested config formats
            if "api" in file_config:
                api = file_config["api"]
                config["api_url"] = api.get("url", config["api_url"])
                config["api_key"] = api.get("key", config["api_key"])
            else:
                config["api_url"] = file_config.get("api_url", config["api_url"])
                config["api_key"] = file_config.get("api_key", config["api_key"])
            if "defaults" in file_config:
                # Canonical key is `[defaults].model`; tolerate `default_model`
                # for configs migrated from the older flat layout.
                defaults = file_config["defaults"]
                config["default_model"] = defaults.get("model") or defaults.get("default_model", "")
            else:
                config["default_model"] = file_config.get("default_model", "")

    _config = config
    return config


def get_api_url() -> str:
    return get_config()["api_url"]


def get_api_key() -> str:
    return get_config()["api_key"]


def ensure_config():
    """Create config directory and file if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            '# Forge CLI Configuration\n'
            'api_url = "http://localhost:8000"\n'
            'api_key = ""\n'
        )
