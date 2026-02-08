"""Tests for the tray/app module."""

from __future__ import annotations

from unittest import mock

import pytest

from h4kshot.tray import H4KShotApp, _create_default_icon


class TestCreateDefaultIcon:
    """Test icon creation."""

    def test_creates_rgba_image(self):
        img = _create_default_icon()
        assert img.mode == "RGBA"
        assert img.size == (64, 64)


class TestH4KShotApp:
    """Test app initialization and helpers."""

    def test_init_loads_config(self):
        app = H4KShotApp()
        assert "upload_url" in app.config
        assert "screenshot_hotkey" in app.config
        assert "record_hotkey" in app.config

    def test_parse_hotkey_alt_printscreen(self):
        app = H4KShotApp()
        keys = app._parse_hotkey("<alt>+<print_screen>")
        assert len(keys) == 2

    def test_parse_hotkey_ctrl_alt_printscreen(self):
        app = H4KShotApp()
        keys = app._parse_hotkey("<ctrl>+<alt>+<print_screen>")
        assert len(keys) == 3

    def test_parse_hotkey_single_char(self):
        app = H4KShotApp()
        keys = app._parse_hotkey("<ctrl>+s")
        assert len(keys) == 2

    @mock.patch("h4kshot.tray.upload_file")
    @mock.patch("h4kshot.tray.copy_to_clipboard")
    def test_upload_and_copy_success(self, mock_clip, mock_upload, tmp_path):
        from h4kshot.uploader import UploadResult

        mock_upload.return_value = UploadResult(success=True, url="https://s.h4ks.com/abc.png")
        mock_clip.return_value = True

        app = H4KShotApp()
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG" + b"\x00" * 100)

        app._upload_and_copy(f)
        mock_clip.assert_called_once_with("https://s.h4ks.com/abc.png")

    @mock.patch("h4kshot.tray.upload_file")
    @mock.patch("h4kshot.tray.copy_to_clipboard")
    def test_upload_and_copy_failure(self, mock_clip, mock_upload, tmp_path):
        from h4kshot.uploader import UploadResult

        mock_upload.return_value = UploadResult(success=False, error="Server error")

        app = H4KShotApp()
        f = tmp_path / "test.png"
        f.write_bytes(b"\x00" * 100)

        app._upload_and_copy(f)
        mock_clip.assert_not_called()

    def test_is_recording_initially_false(self):
        app = H4KShotApp()
        assert app._is_recording is False
        assert app._recorder is None
