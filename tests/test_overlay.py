"""Tests for the overlay module."""

from __future__ import annotations

from unittest import mock

import pytest

from h4kshot.overlay import (
    CaptureRegion,
    MODE_AREA,
    MODE_FULLSCREEN,
    MODE_WINDOW,
    _get_active_window_geometry,
    _get_screen_size,
)


class TestCaptureRegion:
    """Test the CaptureRegion dataclass."""

    def test_creation(self):
        r = CaptureRegion(x=10, y=20, width=300, height=200)
        assert r.x == 10
        assert r.y == 20
        assert r.width == 300
        assert r.height == 200

    def test_equality(self):
        a = CaptureRegion(0, 0, 100, 100)
        b = CaptureRegion(0, 0, 100, 100)
        assert a == b

    def test_inequality(self):
        a = CaptureRegion(0, 0, 100, 100)
        b = CaptureRegion(10, 10, 100, 100)
        assert a != b


class TestModeConstants:
    """Test mode string constants."""

    def test_mode_values(self):
        assert MODE_AREA == "area"
        assert MODE_FULLSCREEN == "fullscreen"
        assert MODE_WINDOW == "window"


class TestGetScreenSize:
    """Test screen size detection."""

    @mock.patch("h4kshot.overlay.mss.mss")
    def test_returns_primary_monitor_size(self, mock_mss):
        mock_ctx = mock.MagicMock()
        mock_ctx.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 2160},  # all
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # primary
        ]
        mock_mss.return_value.__enter__ = mock.Mock(return_value=mock_ctx)
        mock_mss.return_value.__exit__ = mock.Mock(return_value=False)

        w, h = _get_screen_size()
        assert w == 1920
        assert h == 1080

    @mock.patch("h4kshot.overlay.mss.mss", side_effect=Exception("no display"))
    def test_fallback_on_error(self, mock_mss):
        w, h = _get_screen_size()
        assert w == 1920
        assert h == 1080


class TestGetActiveWindowGeometry:
    """Test window geometry detection."""

    @mock.patch("h4kshot.overlay.platform.system", return_value="Linux")
    @mock.patch("h4kshot.overlay.shutil.which", side_effect=lambda c: None)
    def test_returns_none_without_tools(self, mock_which, mock_sys):
        result = _get_active_window_geometry()
        assert result is None

    @mock.patch("h4kshot.overlay.platform.system", return_value="Linux")
    @mock.patch("h4kshot.overlay.shutil.which", return_value="/usr/bin/cmd")
    @mock.patch("h4kshot.overlay.subprocess.check_output")
    def test_linux_parses_xwininfo(self, mock_output, mock_which, mock_sys):
        # First call: xdotool getactivewindow
        # Second call: xwininfo -id <wid>
        mock_output.side_effect = [
            b"12345678\n",
            (
                b"  Absolute upper-left X:  100\n"
                b"  Absolute upper-left Y:  200\n"
                b"  Width: 800\n"
                b"  Height: 600\n"
            ),
        ]
        result = _get_active_window_geometry()
        assert result is not None
        assert result.x == 100
        assert result.y == 200
        assert result.width == 800
        assert result.height == 600

    @mock.patch("h4kshot.overlay.platform.system", return_value="FreeBSD")
    def test_unsupported_platform(self, mock_sys):
        result = _get_active_window_geometry()
        assert result is None


class TestRecorderRegionIntegration:
    """Test that the recorder accepts region parameters properly."""

    @mock.patch("h4kshot.recorder.shutil.which", return_value="/usr/bin/ffmpeg")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Linux")
    def test_linux_region_cmd(self, mock_sys, mock_which):
        from h4kshot.recorder import _build_ffmpeg_cmd
        cmd = _build_ffmpeg_cmd("/tmp/out.mp4", region=(100, 200, 640, 480))
        cmd_str = " ".join(cmd)
        assert "-video_size" in cmd
        assert "640x480" in cmd_str
        assert "+100,200" in cmd_str

    @mock.patch("h4kshot.recorder.shutil.which", return_value="/usr/bin/ffmpeg")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Linux")
    def test_linux_fullscreen_cmd(self, mock_sys, mock_which):
        from h4kshot.recorder import _build_ffmpeg_cmd
        cmd = _build_ffmpeg_cmd("/tmp/out.mp4", region=None)
        assert "-video_size" not in cmd

    @mock.patch("h4kshot.recorder.shutil.which", return_value="C:\\ffmpeg.exe")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Windows")
    def test_windows_region_cmd(self, mock_sys, mock_which):
        from h4kshot.recorder import _build_ffmpeg_cmd
        cmd = _build_ffmpeg_cmd("C:\\out.mp4", region=(50, 100, 800, 600))
        assert "-offset_x" in cmd
        assert "-offset_y" in cmd
        assert "-video_size" in cmd

    @mock.patch("h4kshot.recorder.shutil.which", return_value="/usr/local/bin/ffmpeg")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Darwin")
    def test_macos_region_cmd(self, mock_sys, mock_which):
        from h4kshot.recorder import _build_ffmpeg_cmd
        cmd = _build_ffmpeg_cmd("/tmp/out.mp4", region=(10, 20, 500, 400))
        assert "-vf" in cmd
        vf_idx = cmd.index("-vf")
        assert "crop=500:400:10:20" in cmd[vf_idx + 1]

    def test_screen_recorder_accepts_region(self, tmp_path):
        from h4kshot.recorder import ScreenRecorder
        rec = ScreenRecorder(output_path=tmp_path / "vid.mp4", region=(0, 0, 640, 480))
        assert rec.region == (0, 0, 640, 480)

    def test_screen_recorder_default_region_none(self, tmp_path):
        from h4kshot.recorder import ScreenRecorder
        rec = ScreenRecorder(output_path=tmp_path / "vid.mp4")
        assert rec.region is None
