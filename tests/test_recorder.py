"""Tests for the screen recorder module."""

from __future__ import annotations

import shutil
import platform
from pathlib import Path
from unittest import mock

import pytest

from h4kshot.recorder import ScreenRecorder, _build_ffmpeg_cmd, SIZE_LIMIT_BYTES


class TestBuildFfmpegCmd:
    """Test ffmpeg command construction for each platform."""

    @mock.patch("h4kshot.recorder.shutil.which", return_value="/usr/bin/ffmpeg")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Linux")
    def test_linux_cmd(self, mock_sys, mock_which):
        cmd = _build_ffmpeg_cmd("/tmp/out.mp4", framerate=30)
        assert "/usr/bin/ffmpeg" in cmd
        assert "x11grab" in cmd
        assert "/tmp/out.mp4" in cmd

    @mock.patch("h4kshot.recorder.shutil.which", return_value="/usr/local/bin/ffmpeg")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Darwin")
    def test_macos_cmd(self, mock_sys, mock_which):
        cmd = _build_ffmpeg_cmd("/tmp/out.mp4")
        assert "avfoundation" in cmd

    @mock.patch("h4kshot.recorder.shutil.which", return_value="C:\\ffmpeg\\ffmpeg.exe")
    @mock.patch("h4kshot.recorder.platform.system", return_value="Windows")
    def test_windows_cmd(self, mock_sys, mock_which):
        cmd = _build_ffmpeg_cmd("C:\\temp\\out.mp4")
        assert "gdigrab" in cmd

    @mock.patch("h4kshot.recorder.shutil.which", return_value=None)
    def test_ffmpeg_not_found(self, mock_which):
        with pytest.raises(RuntimeError, match="ffmpeg"):
            _build_ffmpeg_cmd("/tmp/out.mp4")


class TestScreenRecorder:
    """Unit tests for ScreenRecorder (mocked subprocess)."""

    def test_init_default_path(self):
        rec = ScreenRecorder()
        assert rec.output_path.suffix == ".mp4"
        assert "h4kshot_rec_" in rec.output_path.name
        # Cleanup
        rec.output_path.unlink(missing_ok=True)

    def test_init_custom_path(self, tmp_path):
        out = tmp_path / "video.mp4"
        rec = ScreenRecorder(output_path=out)
        assert rec.output_path == out

    def test_is_recording_initially_false(self, tmp_path):
        rec = ScreenRecorder(output_path=tmp_path / "vid.mp4")
        assert rec.is_recording is False

    def test_auto_stopped_initially_false(self, tmp_path):
        rec = ScreenRecorder(output_path=tmp_path / "vid.mp4")
        assert rec.auto_stopped is False

    def test_size_limit_is_under_max(self):
        """The recording size limit should be less than the upload limit."""
        from h4kshot.uploader import MAX_FILE_SIZE_BYTES
        assert SIZE_LIMIT_BYTES < MAX_FILE_SIZE_BYTES
        # 1 MB margin
        assert MAX_FILE_SIZE_BYTES - SIZE_LIMIT_BYTES == 1 * 1024 * 1024

    @mock.patch("h4kshot.recorder.shutil.which", return_value=None)
    def test_start_raises_without_ffmpeg(self, mock_which, tmp_path):
        rec = ScreenRecorder(output_path=tmp_path / "vid.mp4")
        with pytest.raises(RuntimeError, match="ffmpeg"):
            rec.start()

    def test_stop_when_not_recording(self, tmp_path):
        """Stopping when not recording should not raise."""
        out = tmp_path / "vid.mp4"
        out.write_bytes(b"")
        rec = ScreenRecorder(output_path=out)
        result = rec.stop()
        assert result == out
