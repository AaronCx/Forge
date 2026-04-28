"""Regression test for QA Finding #9 — set-default-model round-trip."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _reload_config(home: Path):
    """Force the CLI to re-read its config from a fresh HOME path."""
    if "forge.config" in sys.modules:
        del sys.modules["forge.config"]
    import forge.config as cfg

    cfg.CONFIG_DIR = home / ".forge"
    cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.toml"
    cfg._config = None
    return importlib.reload(cfg)


def test_set_default_model_round_trips(tmp_path, monkeypatch):
    """Writing the default model must be visible to the loader."""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = _reload_config(tmp_path)
    cfg.ensure_config()

    # Mirror the writer's canonical layout: [defaults].model = "..."
    cfg.CONFIG_FILE.write_text(
        '[api]\nurl = "http://localhost:8000"\nkey = ""\n\n[defaults]\nmodel = "ollama/llama3.2:3b"\n'
    )
    cfg._config = None
    assert cfg.get_config()["default_model"] == "ollama/llama3.2:3b"

    # Tolerate the legacy `default_model` key for configs written before the fix.
    cfg.CONFIG_FILE.write_text(
        '[api]\nurl = "http://localhost:8000"\nkey = ""\n\n[defaults]\ndefault_model = "claude-haiku-4-5"\n'
    )
    cfg._config = None
    assert cfg.get_config()["default_model"] == "claude-haiku-4-5"
