"""Entry point for H4KShot."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="h4kshot",
        description="Screenshot/screen-recording with auto-upload to s.h4ks.com",
    )
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Fork to the background (Linux/macOS). On Windows, use --install.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install as a background service that starts on login.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove autostart service.",
    )
    args = parser.parse_args()

    if args.install:
        from h4kshot.daemon import install_autostart
        install_autostart()
        return

    if args.uninstall:
        from h4kshot.daemon import uninstall_autostart
        uninstall_autostart()
        return

    if args.daemon:
        from h4kshot.daemon import daemonize
        daemonize()

    from h4kshot.tray import H4KShotApp
    app = H4KShotApp()
    app.run()


if __name__ == "__main__":
    main()
