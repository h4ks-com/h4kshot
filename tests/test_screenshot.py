"""Tests for the screenshot module."""

from __future__ import annotations

import platform
from pathlib import Path
from unittest import mock

import pytest


class TestCaptureScreenshot:
    """Tests for screenshot capture (requires a display on CI)."""

    @pytest.mark.skipif(
        platform.system() == "Linux"
        and not __import__("os").environ.get("DISPLAY")
        and not __import__("os").environ.get("WAYLAND_DISPLAY"),
        reason="No display available (headless Linux)",
    )
    def test_capture_to_file(self, tmp_path):
        from h4kshot.screenshot import capture_screenshot

        output = tmp_path / "screenshot.png"
        result = capture_screenshot(output_path=output)
        assert result.exists()
        assert result.stat().st_size > 0
        assert result.suffix == ".png"

    @pytest.mark.skipif(
        platform.system() == "Linux"
        and not __import__("os").environ.get("DISPLAY")
        and not __import__("os").environ.get("WAYLAND_DISPLAY"),
        reason="No display available (headless Linux)",
    )
    def test_capture_to_temp(self):
        from h4kshot.screenshot import capture_screenshot

        result = capture_screenshot()
        assert result.exists()
        assert result.stat().st_size > 0
        # Cleanup
        result.unlink(missing_ok=True)

    def test_capture_screenshot_import(self):
        """Ensure the module can be imported on all platforms."""
        from h4kshot.screenshot import capture_screenshot, capture_region
        assert callable(capture_screenshot)
        assert callable(capture_region)
