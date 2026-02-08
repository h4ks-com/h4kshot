# H4KShot

[![CI](https://github.com/h4ks-com/h4kshot/actions/workflows/ci.yml/badge.svg)](https://github.com/h4ks-com/h4kshot/actions/workflows/ci.yml)

Multiplatform screenshot/screen-recording utility with auto-upload to [s.h4ks.com](https://s.h4ks.com) and clipboard link copying.

## Features

- **Screenshot capture** – Take a screenshot with a single hotkey (default: `Alt+PrintScreen`)
- **Screen recording** – Hold the hotkey to start recording; release to stop. Automatically stops just before the 64 MB upload limit.
- **Auto-upload** – Captured files are uploaded to [s.h4ks.com](https://s.h4ks.com) and the share URL is copied to your clipboard.
- **System tray** – Tray icon with options to change keybindings and exit.
- **Cross-platform** – Works on Windows, Linux, and macOS.

## Requirements

- Python 3.9+
- **ffmpeg** must be installed and on `PATH` for screen recording.
- On Linux: `xdotool`, `xclip` or `xsel` for clipboard support.

## Installation

```bash
pip install .
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

```bash
h4kshot          # Launch from terminal
h4kshot-gui      # Launch as GUI app (no console window on Windows)
```

The app starts minimized to the system tray.

### Default Keybindings

| Action | Keybinding |
|--------|-----------|
| Screenshot | `Alt + PrintScreen` |
| Screen Record (toggle) | `Ctrl + Alt + PrintScreen` |

### Tray Menu

- **Change Keybindings** – Opens a dialog to reconfigure hotkeys
- **Exit** – Quit the application

## How It Works

1. Press the hotkey to capture a screenshot (PNG) or start/stop a screen recording (MP4).
2. The file is uploaded via `POST` to `https://s.h4ks.com` (multipart form, field name `file`).
3. The returned URL is copied to your clipboard.
4. Screen recordings auto-stop when the file approaches 64 MB (the server limit).

## Configuration

Settings are stored in `~/.config/h4kshot/config.json` (Linux/macOS) or `%APPDATA%\h4kshot\config.json` (Windows).

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
