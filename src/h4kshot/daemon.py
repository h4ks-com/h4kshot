"""Autostart and daemon utilities for H4KShot.

Provides:
- `h4kshot --install`  – Install as a background service (autostart on login)
- `h4kshot --uninstall` – Remove autostart
- `h4kshot --daemon`   – Fork to background (Linux/macOS)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from h4kshot.config import get_config_dir


def _get_executable() -> str:
    """Return the path to the h4kshot executable."""
    # If installed via pip, the entry-point script is on PATH
    h4kshot_bin = shutil.which("h4kshot")
    if h4kshot_bin:
        return h4kshot_bin
    # Fallback: invoke via python -m
    return f"{sys.executable} -m h4kshot.app"


# ------------------------------------------------------------------ #
# Linux: systemd user service
# ------------------------------------------------------------------ #

def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "h4kshot.service"


def _install_linux() -> None:
    exe = _get_executable()
    unit = textwrap.dedent(f"""\
        [Unit]
        Description=H4KShot – Screenshot & Recording Uploader
        After=graphical-session.target

        [Service]
        Type=simple
        ExecStart={exe}
        Restart=on-failure
        RestartSec=3
        Environment=DISPLAY=:0

        [Install]
        WantedBy=default.target
    """)

    unit_path = _systemd_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(unit, encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "h4kshot.service"], check=True)
    print(f"✅ Installed systemd user service: {unit_path}")
    print("   H4KShot will start automatically on login.")
    print("   Status: systemctl --user status h4kshot")


def _uninstall_linux() -> None:
    unit_path = _systemd_unit_path()
    subprocess.run(["systemctl", "--user", "disable", "--now", "h4kshot.service"],
                    check=False)
    if unit_path.exists():
        unit_path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print("✅ H4KShot autostart removed.")


# ------------------------------------------------------------------ #
# macOS: launchd plist
# ------------------------------------------------------------------ #

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.h4ks.h4kshot.plist"


def _install_macos() -> None:
    exe = _get_executable()
    # Split executable into program + args for launchd
    parts = exe.split()
    program = parts[0]
    args_xml = "\n".join(f"        <string>{p}</string>" for p in parts)

    plist = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>com.h4ks.h4kshot</string>
            <key>ProgramArguments</key>
            <array>
        {args_xml}
            </array>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <true/>
            <key>StandardOutPath</key>
            <string>/tmp/h4kshot.log</string>
            <key>StandardErrorPath</key>
            <string>/tmp/h4kshot.log</string>
        </dict>
        </plist>
    """)

    plist_path = _launchd_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist, encoding="utf-8")

    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    print(f"✅ Installed launchd agent: {plist_path}")
    print("   H4KShot will start automatically on login.")


def _uninstall_macos() -> None:
    plist_path = _launchd_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
    print("✅ H4KShot autostart removed.")


# ------------------------------------------------------------------ #
# Windows: Start Menu Startup folder shortcut
# ------------------------------------------------------------------ #

def _startup_shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "H4KShot.vbs"


def _install_windows() -> None:
    exe = _get_executable()
    # Use a VBS wrapper to launch without a console window
    vbs = textwrap.dedent(f"""\
        Set WshShell = CreateObject("WScript.Shell")
        WshShell.Run "{exe}", 0, False
    """)
    shortcut_path = _startup_shortcut_path()
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    shortcut_path.write_text(vbs, encoding="utf-8")
    print(f"✅ Installed startup script: {shortcut_path}")
    print("   H4KShot will start automatically on login.")


def _uninstall_windows() -> None:
    shortcut_path = _startup_shortcut_path()
    if shortcut_path.exists():
        shortcut_path.unlink()
    print("✅ H4KShot autostart removed.")


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def install_autostart() -> None:
    """Install H4KShot as a background service that starts on login."""
    system = platform.system()
    if system == "Linux":
        _install_linux()
    elif system == "Darwin":
        _install_macos()
    elif system == "Windows":
        _install_windows()
    else:
        print(f"❌ Unsupported platform: {system}")
        sys.exit(1)


def uninstall_autostart() -> None:
    """Remove H4KShot autostart."""
    system = platform.system()
    if system == "Linux":
        _uninstall_linux()
    elif system == "Darwin":
        _uninstall_macos()
    elif system == "Windows":
        _uninstall_windows()
    else:
        print(f"❌ Unsupported platform: {system}")
        sys.exit(1)


def daemonize() -> None:
    """Fork the process to the background (Linux/macOS only).

    On Windows this is a no-op – use --install instead for background running.
    """
    system = platform.system()
    if system == "Windows":
        # On Windows, pythonw.exe already runs without a console.
        # If invoked from cmd, we just continue.
        return

    # Unix double-fork
    try:
        pid = os.fork()
        if pid > 0:
            print(f"H4KShot started in background (PID {pid})")
            sys.exit(0)
    except OSError as e:
        print(f"Fork failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Decouple from parent
    os.setsid()

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        print(f"Second fork failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, sys.stdin.fileno())

    # Keep stdout/stderr for logging to a file if desired
    log_path = get_config_dir() / "h4kshot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(log_fd, sys.stdout.fileno())
    os.dup2(log_fd, sys.stderr.fileno())
    os.close(devnull)
    os.close(log_fd)
