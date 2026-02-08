"""System tray icon and hotkey management for H4KShot."""

from __future__ import annotations

import platform
import sys
import threading
from pathlib import Path

from h4kshot.clipboard import copy_to_clipboard
from h4kshot.config import load_config, save_config
from h4kshot.overlay import (
    CaptureRegion,
    MODE_AREA,
    MODE_FULLSCREEN,
    MODE_WINDOW,
    show_capture_toolbar,
)
from h4kshot.recorder import ScreenRecorder
from h4kshot.screenshot import capture_region, capture_screenshot
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


def _create_stop_icon():
    """Create a red circle stop-recording tray icon."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Red circle
    draw.ellipse([4, 4, 60, 60], fill=(220, 30, 30, 255))
    # White square (stop symbol)
    draw.rectangle([20, 20, 44, 44], fill=(255, 255, 255, 255))
    return img


def _save_icon_to_temp(img=None) -> str:
    """Save a tray icon to a temp file and return its path (needed by AppIndicator)."""
    import tempfile
    import os

    if img is None:
        img = _create_default_icon()
    fd, path = tempfile.mkstemp(suffix=".png", prefix="h4kshot_icon_")
    os.close(fd)
    img.save(path, "PNG")
    return path


def _ensure_gi_importable():
    """Make sure PyGObject (gi) is importable even inside a venv."""
    try:
        import gi  # noqa: F401
    except ImportError:
        for extra in ["/usr/lib/python3/dist-packages", "/usr/lib64/python3/dist-packages"]:
            if extra not in sys.path:
                sys.path.insert(0, extra)


def _is_gtk_available() -> bool:
    """Check if GTK3 + AppIndicator are available (Linux)."""
    try:
        _ensure_gi_importable()
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import Gtk, AyatanaAppIndicator3  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


class H4KShotApp:
    """Main application managing the tray icon, hotkeys, and capture logic."""

    def __init__(self):
        self.config = load_config()
        self._recorder: ScreenRecorder | None = None
        self._is_recording = False
        self._hotkey_listener = None
        self._tray_icon = None
        self._stop_indicator = None  # second tray icon for stop-recording
        self._using_gtk = False  # True when running with GTK main loop

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
        """Show the capture toolbar and take a screenshot based on mode."""

        def _on_screenshot(mode: str, region: CaptureRegion | None):
            try:
                if mode == MODE_AREA and region:
                    path = capture_region(region.x, region.y, region.width, region.height)
                else:
                    path = capture_screenshot()
                threading.Thread(
                    target=self._upload_and_copy, args=(path,), daemon=True
                ).start()
            except Exception as e:
                self._notify(f"Screenshot failed: {e}")

        # The toolbar creates GTK windows, so it MUST run on the GTK main
        # thread.  When called from a hotkey listener (background thread) we
        # schedule it via GLib.idle_add; otherwise call directly.
        def _show():
            show_capture_toolbar(
                _on_screenshot, lambda m, r: self._start_recording(m, r)
            )

        self._run_on_gtk_thread(_show)

    # ------------------------------------------------------------------ #
    # Screen recording
    # ------------------------------------------------------------------ #
    def _run_on_gtk_thread(self, func: callable) -> None:
        """Schedule *func* to run on the GTK main thread (if using GTK)."""
        if self._using_gtk:
            _ensure_gi_importable()
            from gi.repository import GLib
            GLib.idle_add(func)
        else:
            func()

    def _start_recording(self, mode: str, region: CaptureRegion | None) -> None:
        """Start recording (called from overlay toolbar)."""
        if self._is_recording:
            return
        try:
            rec_region = None
            if mode == MODE_AREA and region:
                rec_region = (region.x, region.y, region.width, region.height)
            elif mode == MODE_WINDOW and region:
                rec_region = (region.x, region.y, region.width, region.height)

            self._recorder = ScreenRecorder(region=rec_region)
            self._recorder.start()
            self._is_recording = True
            self._notify("Recording started… (use hotkey, tray, or ⏹ button to stop)")

            # Show a second tray icon (red circle) for stopping
            self._run_on_gtk_thread(self._show_stop_tray_icon)

        except RuntimeError as e:
            self._notify(str(e))

        self._run_on_gtk_thread(self._update_gtk_record_items)

    def toggle_recording(self) -> None:
        """Start or stop screen recording."""
        if self._is_recording and self._recorder:
            self._is_recording = False
            output = self._recorder.stop()
            self._recorder = None

            # Hide the stop-recording tray icon
            self._run_on_gtk_thread(self._hide_stop_tray_icon)

            self._notify("Recording stopped – uploading…")
            threading.Thread(target=self._upload_and_copy, args=(output,), daemon=True).start()
        else:
            # When triggered via hotkey (not toolbar), start fullscreen recording.
            # _start_recording touches GTK (shows stop tray icon), so schedule
            # on the main thread.
            self._run_on_gtk_thread(
                lambda: self._start_recording(MODE_FULLSCREEN, None)
            )

        # Update GTK tray menu items
        self._run_on_gtk_thread(self._update_gtk_record_items)
        # Update pystray menu (forces re-render of dynamic label)
        if self._tray_icon and hasattr(self._tray_icon, 'update_menu'):
            try:
                self._tray_icon.update_menu()
            except Exception:
                pass

    def _update_gtk_record_items(self) -> None:
        """Sync GTK menu item sensitivity with recording state.

        MUST be called on the GTK main thread (use _run_on_gtk_thread).
        """
        try:
            rec = getattr(self, '_gtk_item_record', None)
            stop = getattr(self, '_gtk_item_stop', None)
            if rec and stop:
                rec.set_sensitive(not self._is_recording)
                stop.set_sensitive(self._is_recording)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Stop-recording tray icon (second indicator)
    # ------------------------------------------------------------------ #
    def _show_stop_tray_icon(self) -> None:
        """Show a second tray icon (red ⏹) for stopping the recording.

        MUST be called on the GTK main thread.
        """
        if self._stop_indicator is not None:
            return  # already visible

        system = platform.system()
        if system == "Linux" and _is_gtk_available():
            self._show_stop_tray_icon_gtk()
        # On macOS/Windows pystray handles it via the dynamic menu label

    def _show_stop_tray_icon_gtk(self) -> None:
        _ensure_gi_importable()
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import Gtk, AyatanaAppIndicator3

        stop_icon_path = _save_icon_to_temp(_create_stop_icon())

        indicator = AyatanaAppIndicator3.Indicator.new(
            "h4kshot-stop",
            stop_icon_path,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        indicator.set_title("Stop Recording")

        menu = Gtk.Menu()
        item_stop = Gtk.MenuItem(label="⏹  Stop Recording")
        item_stop.connect("activate", lambda _: self.toggle_recording())
        menu.append(item_stop)
        menu.show_all()
        indicator.set_menu(menu)

        self._stop_indicator = indicator

    def _hide_stop_tray_icon(self) -> None:
        """Remove the stop-recording tray icon.

        MUST be called on the GTK main thread.
        """
        if self._stop_indicator is not None:
            try:
                _ensure_gi_importable()
                import gi
                gi.require_version("AyatanaAppIndicator3", "0.1")
                from gi.repository import AyatanaAppIndicator3
                self._stop_indicator.set_status(
                    AyatanaAppIndicator3.IndicatorStatus.PASSIVE
                )
            except Exception:
                pass
            self._stop_indicator = None

    # ------------------------------------------------------------------ #
    # Notifications (best-effort)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _notify(message: str) -> None:
        """Show a desktop notification (best-effort, non-blocking)."""
        print(f"[h4kshot] {message}", flush=True)
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
        """Parse a hotkey string like '<alt>+<print_screen>' into a pynput key list."""
        from pynput.keyboard import Key, KeyCode

        parts = [p.strip() for p in hotkey_str.split("+")]
        keys = []
        for part in parts:
            part_lower = part.lower().strip("<>")
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
        # Sort combos so the more specific (longer) one is checked first.
        # This prevents <alt>+<print_screen> from firing when the user
        # actually pressed <ctrl>+<alt>+<print_screen>.
        combos = sorted(
            [
                (screenshot_combo, self.take_screenshot),
                (record_combo, self.toggle_recording),
            ],
            key=lambda pair: len(pair[0]),
            reverse=True,
        )

        def on_press(key):
            try:
                current_keys.add(str(key))
            except Exception:
                pass
            for combo, action in combos:
                if combo.issubset(current_keys):
                    action()
                    break

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
    # Keybinding change dialog
    # ------------------------------------------------------------------ #
    def _open_keybinding_dialog(self, *_args) -> None:
        """Open a dialog to change keybindings.

        Uses GTK on Linux (if available) or Tkinter elsewhere.
        """
        system = platform.system()
        if system == "Linux" and _is_gtk_available():
            # GTK dialog must run on the main thread via GLib.idle_add
            # but we're called from a menu signal, so it's already on the GTK thread
            self._keybinding_dialog_gtk()
        else:
            threading.Thread(target=self._keybinding_dialog_tk, daemon=True).start()

    def _keybinding_dialog_gtk(self) -> None:
        """GTK3 keybinding dialog for Linux."""
        _ensure_gi_importable()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        dialog = Gtk.Dialog(
            title="H4KShot – Keybindings",
            flags=0,
        )
        dialog.set_default_size(450, 180)
        dialog.set_resizable(False)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(15)
        content.set_margin_end(15)
        content.set_margin_top(10)

        # Screenshot hotkey
        hbox1 = Gtk.Box(spacing=10)
        lbl1 = Gtk.Label(label="Screenshot Hotkey:")
        hbox1.pack_start(lbl1, False, False, 0)
        screenshot_entry = Gtk.Entry()
        screenshot_entry.set_text(self.config["screenshot_hotkey"])
        screenshot_entry.set_hexpand(True)
        hbox1.pack_start(screenshot_entry, True, True, 0)
        content.pack_start(hbox1, False, False, 5)

        # Record hotkey
        hbox2 = Gtk.Box(spacing=10)
        lbl2 = Gtk.Label(label="Record Hotkey:")
        hbox2.pack_start(lbl2, False, False, 0)
        record_entry = Gtk.Entry()
        record_entry.set_text(self.config["record_hotkey"])
        record_entry.set_hexpand(True)
        hbox2.pack_start(record_entry, True, True, 0)
        content.pack_start(hbox2, False, False, 5)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.config["screenshot_hotkey"] = screenshot_entry.get_text()
            self.config["record_hotkey"] = record_entry.get_text()
            save_config(self.config)
            self._stop_hotkeys()
            self._start_hotkeys()
            self._notify("Keybindings saved! New hotkeys are active.")

        dialog.destroy()

    def _keybinding_dialog_tk(self) -> None:
        """Tkinter keybinding dialog (macOS / Windows / fallback)."""
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.title("H4KShot – Keybindings")
        root.geometry("420x200")
        root.resizable(False, False)

        # Bring to front
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()

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
            self._stop_hotkeys()
            self._start_hotkeys()
            messagebox.showinfo("H4KShot", "Keybindings saved! New hotkeys are active.")
            root.destroy()

        tk.Button(root, text="Save", command=on_save, width=12).grid(
            row=2, column=0, columnspan=2, pady=15
        )

        root.mainloop()

    # ------------------------------------------------------------------ #
    # Tray icon
    # ------------------------------------------------------------------ #
    def _quit(self, *_args) -> None:
        """Exit the application."""
        self._stop_hotkeys()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        sys.exit(0)

    def run(self) -> None:
        """Start the application with the best available tray backend."""
        system = platform.system()

        self._start_hotkeys()

        if system == "Linux" and _is_gtk_available():
            self._run_gtk_tray()
        else:
            self._run_pystray()

    def _run_pystray(self) -> None:
        """Run with pystray (works on macOS/Windows, fallback on Linux)."""
        import pystray
        from pystray import MenuItem

        icon_image = _create_default_icon()
        menu = pystray.Menu(
            MenuItem("📷  Capture…", lambda icon, item: self.take_screenshot()),
            MenuItem(
                lambda item: "⏹️ Stop Recording" if self._is_recording else "🎥 Start Recording",
                lambda icon, item: self.toggle_recording(),
            ),
            pystray.Menu.SEPARATOR,
            MenuItem("Change Keybindings", lambda icon, item: self._open_keybinding_dialog()),
            pystray.Menu.SEPARATOR,
            MenuItem("Exit", lambda icon, item: self._quit()),
        )

        self._tray_icon = pystray.Icon("h4kshot", icon_image, "H4KShot", menu)
        self._tray_icon.run()

    def _run_gtk_tray(self) -> None:
        """Run with GTK3 AppIndicator (Linux – proper menu support)."""
        _ensure_gi_importable()
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import Gtk, AyatanaAppIndicator3

        self._using_gtk = True

        # Save icon to temp file (AppIndicator needs a file path)
        icon_path = _save_icon_to_temp()

        indicator = AyatanaAppIndicator3.Indicator.new(
            "h4kshot",
            icon_path,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        indicator.set_title("H4KShot")

        # Build menu
        menu = Gtk.Menu()

        item_capture = Gtk.MenuItem(label="📷  Capture…")
        item_capture.connect("activate", lambda _: self.take_screenshot())
        menu.append(item_capture)

        item_record = Gtk.MenuItem(label="🎥  Start Recording")
        item_stop = Gtk.MenuItem(label="⏹️  Stop Recording")
        item_stop.set_sensitive(False)  # disabled until recording starts

        def _on_start_record(_widget):
            self.toggle_recording()
            if self._is_recording:
                item_record.set_sensitive(False)
                item_stop.set_sensitive(True)

        def _on_stop_record(_widget):
            self.toggle_recording()
            if not self._is_recording:
                item_record.set_sensitive(True)
                item_stop.set_sensitive(False)

        item_record.connect("activate", _on_start_record)
        item_stop.connect("activate", _on_stop_record)
        menu.append(item_record)
        menu.append(item_stop)

        menu.append(Gtk.SeparatorMenuItem())

        item_keybindings = Gtk.MenuItem(label="⌨️  Change Keybindings")
        item_keybindings.connect("activate", lambda _: self._open_keybinding_dialog())
        menu.append(item_keybindings)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="❌  Exit")
        item_quit.connect("activate", lambda _: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        indicator.set_menu(menu)

        # Store refs so hotkey toggle can update menu state too
        self._gtk_item_record = item_record
        self._gtk_item_stop = item_stop

        self._tray_icon = indicator
        Gtk.main()
