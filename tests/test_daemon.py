"""Tests for the daemon/autostart module."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from unittest import mock

import pytest

from h4kshot.daemon import (
    _get_executable,
    _systemd_unit_path,
    install_autostart,
    uninstall_autostart,
)


class TestGetExecutable:
    def test_returns_string(self):
        exe = _get_executable()
        assert isinstance(exe, str)
        assert len(exe) > 0


class TestSystemdUnitPath:
    def test_path_is_in_home(self):
        path = _systemd_unit_path()
        assert "systemd" in str(path)
        assert path.name == "h4kshot.service"


class TestInstallAutostart:
    @mock.patch("h4kshot.daemon.platform.system", return_value="Linux")
    @mock.patch("h4kshot.daemon._install_linux")
    def test_install_linux(self, mock_install, mock_sys):
        install_autostart()
        mock_install.assert_called_once()

    @mock.patch("h4kshot.daemon.platform.system", return_value="Darwin")
    @mock.patch("h4kshot.daemon._install_macos")
    def test_install_macos(self, mock_install, mock_sys):
        install_autostart()
        mock_install.assert_called_once()

    @mock.patch("h4kshot.daemon.platform.system", return_value="Windows")
    @mock.patch("h4kshot.daemon._install_windows")
    def test_install_windows(self, mock_install, mock_sys):
        install_autostart()
        mock_install.assert_called_once()


class TestUninstallAutostart:
    @mock.patch("h4kshot.daemon.platform.system", return_value="Linux")
    @mock.patch("h4kshot.daemon._uninstall_linux")
    def test_uninstall_linux(self, mock_uninstall, mock_sys):
        uninstall_autostart()
        mock_uninstall.assert_called_once()

    @mock.patch("h4kshot.daemon.platform.system", return_value="Darwin")
    @mock.patch("h4kshot.daemon._uninstall_macos")
    def test_uninstall_macos(self, mock_uninstall, mock_sys):
        uninstall_autostart()
        mock_uninstall.assert_called_once()

    @mock.patch("h4kshot.daemon.platform.system", return_value="Windows")
    @mock.patch("h4kshot.daemon._uninstall_windows")
    def test_uninstall_windows(self, mock_uninstall, mock_sys):
        uninstall_autostart()
        mock_uninstall.assert_called_once()


class TestDaemonize:
    @mock.patch("h4kshot.daemon.platform.system", return_value="Windows")
    def test_noop_on_windows(self, mock_sys):
        """daemonize() should be a no-op on Windows."""
        from h4kshot.daemon import daemonize
        # Should not raise, should not fork
        daemonize()
