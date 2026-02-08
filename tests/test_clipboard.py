"""Tests for the clipboard module."""

from __future__ import annotations

import platform
import subprocess
from unittest import mock

import pytest

from h4kshot.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    """Test clipboard functionality across platforms (mocked)."""

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Darwin")
    @mock.patch("h4kshot.clipboard.subprocess.run")
    def test_macos_pbcopy(self, mock_run, mock_sys):
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = copy_to_clipboard("https://s.h4ks.com/test.png")
        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0] == ["pbcopy"]

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Windows")
    @mock.patch("h4kshot.clipboard.subprocess.run")
    def test_windows_clip(self, mock_run, mock_sys):
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = copy_to_clipboard("https://s.h4ks.com/test.png")
        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0] == ["clip.exe"]

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Linux")
    @mock.patch("h4kshot.clipboard.shutil.which", return_value="/usr/bin/xclip")
    @mock.patch("h4kshot.clipboard.subprocess.run")
    def test_linux_xclip(self, mock_run, mock_which, mock_sys):
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = copy_to_clipboard("https://s.h4ks.com/test.png")
        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "xclip" in args[0][0]

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Linux")
    @mock.patch("h4kshot.clipboard.shutil.which", side_effect=lambda cmd: "/usr/bin/xsel" if cmd == "xsel" else None)
    @mock.patch("h4kshot.clipboard.subprocess.run")
    def test_linux_xsel_fallback(self, mock_run, mock_which, mock_sys):
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = copy_to_clipboard("https://s.h4ks.com/test.png")
        assert result is True

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Linux")
    @mock.patch("h4kshot.clipboard.shutil.which", side_effect=lambda cmd: "/usr/bin/wl-copy" if cmd == "wl-copy" else None)
    @mock.patch("h4kshot.clipboard.subprocess.run")
    def test_linux_wl_copy_fallback(self, mock_run, mock_which, mock_sys):
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = copy_to_clipboard("https://s.h4ks.com/test.png")
        assert result is True

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Linux")
    @mock.patch("h4kshot.clipboard.shutil.which", return_value=None)
    def test_fallback_to_pyperclip(self, mock_which, mock_sys):
        with mock.patch("pyperclip.copy") as mock_copy:
            result = copy_to_clipboard("test")
            assert result is True
            mock_copy.assert_called_once_with("test")

    @mock.patch("h4kshot.clipboard.platform.system", return_value="Linux")
    @mock.patch("h4kshot.clipboard.shutil.which", return_value=None)
    def test_total_failure(self, mock_which, mock_sys):
        with mock.patch("pyperclip.copy", side_effect=Exception("fail")):
            result = copy_to_clipboard("test")
            assert result is False
