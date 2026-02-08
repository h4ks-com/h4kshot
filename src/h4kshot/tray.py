"""System tray icon and hotkey management for H4KShot."""

from __future__ import annotations

import platform
import sys
import threading
from pathlib import Path

from h4kshot.clipboard import copy_to_clipboard
from h4kshot.config import load_config, save_config
from h4kshot.recorder import ScreenRecorder
from h4kshot.screenshot import capture_screenshot
from h4kshot.uploader import upload_file


def _create_default_icon():
    """Create a simple default tray icon image."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Camera-like icon
    draw.rounded_rectangle([4, 14, 60, 54], radius=8, fill=(50, 120, 220, 255))
    draw.ellipse([22, 22, 42, 46], fill=(255, 255, 255, 255))
    draw.ellipse([26, 26, 38, 42], fill=(50, 120, 220, 255))
    # Flash
    draw.rectangle([24, 6, 40, 16], fill=(50, 120, 220, 255))
    return img


class H4KShotApp:
    """Main application managing the tray icon, hotkeys, and capture logic."""

    def __init__(self):
        self.config = load_config()
        self._recorder: ScreenRecorder | None = None
        self._is_recording = False
        self._hotkey_listener = None
        self._tray_icon = None

    # ------------------------------------------------------------------ #
    # Upload helper
    # ------------------------------------------------------------------ #
    def _upload_and_copy(self, file_path: Path) -> None:
        """Upload a file and copy the resulting URL to the clipboard."""
        result = upload_file(file_path, upload_url=self.config["upload_url"])
        if result.success and result.url:
            copy_to_clipboard(result.url)
            self._notify(f"Uploaded! URL copied:\n{result.url}")
        else:
            self._notify(f"Upload failed: {result.error}")

        # Clean up temp file
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Screenshot
    # ------------------------------------------------------------------ #
    def take_screenshot(self) -> None:
        """Capture a screenshot, upload it, and copy the URL."""
        try:
            path = capture_screenshot()
            threading.Thread(target=self._upload_and_copy, args=(path,), daemon=True).start()
        except Exception as e:
            self._notify(f"Screenshot failed: {e}")

    # ------------------------------------------------------------------ #
    # Screen recording
    # ------------------------------------------------------------------ #
    def toggle_recording(self) -> None:
        """Start or stop screen recording."""
        if self._is_recording and self._recorder:
            self._is_recording = False
            output = self._recorder.stop()
            self._notify("Recording stopped – uploading…")
            threading.Thread(target=self._upload_and_copy, args=(output,), daemon=True).start()
            self._recorder = None
        else:
            try:
                self._recorder = ScreenRecorder()
                self._recorder.start()
                self._is_recording = True
                self._notify("Recording started…")
            except RuntimeError as e:
                self._notify(str(e))

    # ------------------------------------------------------------------ #
    # Notifications (best-effort)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _notify(message: str) -> None:
        """Show a desktop notification (best-effort, non-blocking)."""
        print(f"[h4kshot] {message}")
        try:
            system = platform.system()
            if system == "Linux":
                import subprocess
                subprocess.Popen(
                    ["notify-send", "H4KShot", message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif system == "Darwin":
                import subprocess
                subprocess.Popen(
                    [
                        "osascript", "-e",
                        f'display notification "{message}" with title "H4KShot"',
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Hotkey management
    # ------------------------------------------------------------------ #
    def _parse_hotkey(self, hotkey_str: str):
        """Parse a hotkey string like '<alt>+<print_screen>' into a pynput HotKey set."""
        from pynput.keyboard import HotKey, Key, KeyCode

        parts = [p.strip() for p in hotkey_str.split("+")]
        keys = []
        for part in parts:
            part_lower = part.lower().strip("<>")
            # Map common names to pynput Keys
            key_map = {
                "alt": Key.alt,
                "alt_l": Key.alt_l,
                "alt_r": Key.alt_r,
                "ctrl": Key.ctrl,
                "ctrl_l": Key.ctrl_l,
                "ctrl_r": Key.ctrl_r,
                "shift": Key.shift,
                "shift_l": Key.shift_l,
                "shift_r": Key.shift_r,
                "print_screen": Key.print_screen,
                "printscreen": Key.print_screen,
                "cmd": Key.cmd,
                "super": Key.cmd,
            }
            if part_lower in key_map:
                keys.append(key_map[part_lower])
            elif len(part_lower) == 1:
                keys.append(KeyCode.from_char(part_lower))
            else:
                # Try as Key attribute
                try:
                    keys.append(getattr(Key, part_lower))
                except AttributeError:
                    keys.append(KeyCode.from_char(part_lower))
        return keys

    def _start_hotkeys(self) -> None:
        """Register global hotkeys using pynput."""
        from pynput import keyboard

        screenshot_keys = self._parse_hotkey(self.config["screenshot_hotkey"])
        record_keys = self._parse_hotkey(self.config["record_hotkey"])

        screenshot_combo = {str(k) for k in screenshot_keys}
        record_combo = {str(k) for k in record_keys}

        current_keys: set[str] = set()

        def on_press(key):
            try:
                current_keys.add(str(key))
            except Exception:
                pass
            if screenshot_combo.issubset(current_keys):
                self.take_screenshot()
            elif record_combo.issubset(current_keys):
                self.toggle_recording()

        def on_release(key):
            try:
                current_keys.discard(str(key))
            except Exception:
                pass

        self._hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    def _stop_hotkeys(self) -> None:
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

    # ------------------------------------------------------------------ #
    # Keybinding change dialog (Tkinter for cross-platform support)
    # ------------------------------------------------------------------ #
    def _open_keybinding_dialog(self, icon=None, item=None) -> None:
        """Open a simple Tkinter dialog to change keybindings."""
        threading.Thread(target=self._keybinding_dialog_thread, daemon=True).start()

    def _keybinding_dialog_thread(self) -> None:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("H4KShot – Keybindings")
        root.geometry("420x200")
        root.resizable(False, False)

        tk.Label(root, text="Screenshot Hotkey:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        screenshot_var = tk.StringVar(value=self.config["screenshot_hotkey"])
        tk.Entry(root, textvariable=screenshot_var, width=30).grid(row=0, column=1, padx=10, pady=10)

        tk.Label(root, text="Record Hotkey:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        record_var = tk.StringVar(value=self.config["record_hotkey"])
        tk.Entry(root, textvariable=record_var, width=30).grid(row=1, column=1, padx=10, pady=10)

        def on_save():
            self.config["screenshot_hotkey"] = screenshot_var.get()
            self.config["record_hotkey"] = record_var.get()
            save_config(self.config)
            # Restart hotkeys
            self._stop_hotkeys()
            self._start_hotkeys()
            messagebox.showinfo("H4KShot", "Keybindings saved! New hotkeys are active.")
            root.destroy()

        tk.Button(root, text="Save", command=on_save, width=12).grid(row=2, column=0, columnspan=2, pady=15)

        root.mainloop()

    # ------------------------------------------------------------------ #
    # Tray icon
    # ------------------------------------------------------------------ #
    def _quit(self, icon=None, item=None) -> None:
        """Exit the application."""
        self._stop_hotkeys()
        if self._tray_icon:
            self._tray_icon.stop()
        sys.exit(0)

    def run(self) -> None:
        """Start the application: tray icon + hotkey listener."""
        import pystray
        from pystray import MenuItem

        self._start_hotkeys()

        icon_image = _create_default_icon()
        menu = pystray.Menu(
            MenuItem("Take Screenshot", lambda icon, item: self.take_screenshot()),
            MenuItem("Toggle Recording", lambda icon, item: self.toggle_recording()),
            pystray.Menu.SEPARATOR,
            MenuItem("Change Keybindings", self._open_keybinding_dialog),
            pystray.Menu.SEPARATOR,
            MenuItem("Exit", self._quit),
        )

        self._tray_icon = pystray.Icon("h4kshot", icon_image, "H4KShot", menu)
        self._tray_icon.run()
