"""Tests for the configuration module."""

import json
import os
import platform
from pathlib import Path
from unittest import mock

import pytest

from h4kshot.config import (
    DEFAULT_CONFIG,
    get_config_dir,
    get_config_path,
    load_config,
    save_config,
)


class TestGetConfigDir:
    """Tests for get_config_dir across platforms."""

    @mock.patch("h4kshot.config.platform.system", return_value="Windows")
    @mock.patch.dict(os.environ, {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"})
    def test_windows(self, mock_sys):
        result = get_config_dir()
        assert result == Path("C:\\Users\\test\\AppData\\Roaming") / "h4kshot"

    @mock.patch("h4kshot.config.platform.system", return_value="Darwin")
    def test_macos(self, mock_sys):
        result = get_config_dir()
        assert "h4kshot" in str(result)
        assert "Library" in str(result) or ".config" in str(result) or "h4kshot" in str(result)

    @mock.patch("h4kshot.config.platform.system", return_value="Linux")
    @mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/home/test/.config"})
    def test_linux_xdg(self, mock_sys):
        result = get_config_dir()
        assert result == Path("/home/test/.config/h4kshot")

    @mock.patch("h4kshot.config.platform.system", return_value="Linux")
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_linux_no_xdg(self, mock_sys):
        result = get_config_dir()
        assert "h4kshot" in str(result)


class TestLoadSaveConfig:
    """Tests for loading and saving configuration."""

    def test_load_defaults(self, tmp_path):
        """When no config file exists, defaults are returned."""
        with mock.patch("h4kshot.config.get_config_path", return_value=tmp_path / "nonexistent.json"):
            config = load_config()
        assert config == DEFAULT_CONFIG

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        with mock.patch("h4kshot.config.get_config_path", return_value=config_file):
            custom = dict(DEFAULT_CONFIG)
            custom["screenshot_hotkey"] = "<ctrl>+<shift>+s"
            save_config(custom)

            loaded = load_config()
            assert loaded["screenshot_hotkey"] == "<ctrl>+<shift>+s"

    def test_load_corrupt_file(self, tmp_path):
        """Corrupt JSON falls back to defaults."""
        config_file = tmp_path / "config.json"
        config_file.write_text("NOT VALID JSON {{{")
        with mock.patch("h4kshot.config.get_config_path", return_value=config_file):
            config = load_config()
        assert config == DEFAULT_CONFIG

    def test_save_creates_directory(self, tmp_path):
        config_file = tmp_path / "subdir" / "nested" / "config.json"
        with mock.patch("h4kshot.config.get_config_path", return_value=config_file):
            save_config(DEFAULT_CONFIG)
        assert config_file.exists()

    def test_partial_config_merges_with_defaults(self, tmp_path):
        """A partial config file is merged with defaults."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"upload_url": "https://custom.example.com"}))
        with mock.patch("h4kshot.config.get_config_path", return_value=config_file):
            config = load_config()
        assert config["upload_url"] == "https://custom.example.com"
        assert config["max_file_size_mb"] == DEFAULT_CONFIG["max_file_size_mb"]
