"""Configuration management for H4KShot."""

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    "upload_url": "https://s.h4ks.com/api/",
    "max_file_size_mb": 64,
    "screenshot_hotkey": "<alt>+<print_screen>",
    "record_hotkey": "<ctrl>+<alt>+<print_screen>",
    "notification_enabled": True,
}


def get_config_dir() -> Path:
    """Return the platform-specific config directory."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        return Path(base) / "h4kshot"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "h4kshot"
    else:  # Linux and others
        xdg = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        return Path(xdg) / "h4kshot"


def get_config_path() -> Path:
    """Return the path to the configuration file."""
    return get_config_dir() / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration from disk, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config: dict[str, Any]) -> None:
    """Persist the configuration to disk."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
