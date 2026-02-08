"""Entry point for H4KShot."""

from h4kshot.tray import H4KShotApp


def main() -> None:
    app = H4KShotApp()
    app.run()


if __name__ == "__main__":
    main()
