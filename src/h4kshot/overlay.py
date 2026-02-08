"""Capture overlay UI for H4KShot.

Provides:
- A floating toolbar with screenshot/record buttons and mode switchers
  (area select, full screen, window select)
- A transparent region-selection overlay (click & drag)
- A floating red stop-recording button
- Cross-platform: GTK3 on Linux, Tkinter fallback elsewhere

All windows are top-level, always-on-top, and translucent where possible.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import mss

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CaptureRegion:
    """A rectangular screen region."""
    x: int
    y: int
    width: int
    height: int


# Capture modes
MODE_AREA = "area"
MODE_FULLSCREEN = "fullscreen"
MODE_WINDOW = "window"

# ---------------------------------------------------------------------------
# Cross-platform helpers
# ---------------------------------------------------------------------------

def _get_active_window_geometry() -> CaptureRegion | None:
    """Return the geometry of the currently focused window (best-effort)."""
    system = platform.system()
    try:
        if system == "Linux":
            if shutil.which("xdotool") and shutil.which("xwininfo"):
                wid = subprocess.check_output(
                    ["xdotool", "getactivewindow"], timeout=3
                ).decode().strip()
                info = subprocess.check_output(
                    ["xwininfo", "-id", wid], timeout=3
                ).decode()
                vals: dict[str, int] = {}
                for line in info.splitlines():
                    if "Absolute upper-left X:" in line:
                        vals["x"] = int(line.split(":")[1].strip())
                    elif "Absolute upper-left Y:" in line:
                        vals["y"] = int(line.split(":")[1].strip())
                    elif "Width:" in line:
                        vals["width"] = int(line.split(":")[1].strip())
                    elif "Height:" in line:
                        vals["height"] = int(line.split(":")[1].strip())
                if len(vals) == 4:
                    return CaptureRegion(**vals)
        elif system == "Darwin":
            script = '''
            tell application "System Events"
                set fp to first process whose frontmost is true
                tell fp
                    set {x, y} to position of window 1
                    set {w, h} to size of window 1
                end tell
            end tell
            return (x as text) & "," & (y as text) & "," & (w as text) & "," & (h as text)
            '''
            out = subprocess.check_output(
                ["osascript", "-e", script], timeout=5
            ).decode().strip()
            x, y, w, h = [int(v) for v in out.split(",")]
            return CaptureRegion(x, y, w, h)
    except Exception:
        pass
    return None


def _get_screen_size() -> tuple[int, int]:
    """Return (width, height) of the primary screen."""
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]  # primary monitor
            return mon["width"], mon["height"]
    except Exception:
        return 1920, 1080


# ---------------------------------------------------------------------------
# GTK implementation (Linux)
# ---------------------------------------------------------------------------

def _ensure_gi():
    try:
        import gi  # noqa: F401
    except ImportError:
        for p in ["/usr/lib/python3/dist-packages", "/usr/lib64/python3/dist-packages"]:
            if p not in sys.path:
                sys.path.insert(0, p)


def _gtk_available() -> bool:
    try:
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


class _GtkRegionSelector:
    """Full-screen transparent overlay for click-drag region selection (GTK3)."""

    def __init__(self, callback: Callable[[CaptureRegion | None], None]):
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        self._callback = callback
        self._start_x = self._start_y = 0
        self._cur_x = self._cur_y = 0
        self._dragging = False

        self._win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self._win.set_title("H4KShot – Select Region")
        self._win.set_decorated(False)
        self._win.set_app_paintable(True)
        self._win.set_keep_above(True)
        self._win.fullscreen()

        screen = self._win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._win.set_visual(visual)

        self._win.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self._win.connect("draw", self._on_draw)
        self._win.connect("button-press-event", self._on_press)
        self._win.connect("button-release-event", self._on_release)
        self._win.connect("motion-notify-event", self._on_motion)
        self._win.connect("key-press-event", self._on_key)

        cursor = Gdk.Cursor.new_from_name(self._win.get_display(), "crosshair")
        self._win.show_all()
        self._win.get_window().set_cursor(cursor)

    def _on_draw(self, widget, cr):
        # Semi-transparent dark overlay
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.paint()

        if self._dragging:
            x = min(self._start_x, self._cur_x)
            y = min(self._start_y, self._cur_y)
            w = abs(self._cur_x - self._start_x)
            h = abs(self._cur_y - self._start_y)

            # Clear selected region (make it transparent)
            cr.set_operator(0)  # CAIRO_OPERATOR_CLEAR
            cr.rectangle(x, y, w, h)
            cr.fill()

            # Draw selection border
            import cairo
            cr.set_operator(cairo.OPERATOR_OVER)
            cr.set_source_rgba(0.2, 0.5, 1.0, 0.9)
            cr.set_line_width(2)
            cr.rectangle(x, y, w, h)
            cr.stroke()

            # Dimension label
            label = f"{w} × {h}"
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.set_font_size(14)
            cr.move_to(x + 4, y - 6 if y > 20 else y + h + 16)
            cr.show_text(label)

    def _on_press(self, widget, event):
        self._start_x = int(event.x)
        self._start_y = int(event.y)
        self._dragging = True

    def _on_release(self, widget, event):
        self._dragging = False
        x = min(self._start_x, int(event.x))
        y = min(self._start_y, int(event.y))
        w = abs(int(event.x) - self._start_x)
        h = abs(int(event.y) - self._start_y)
        self._win.destroy()
        if w > 5 and h > 5:
            self._callback(CaptureRegion(x, y, w, h))
        else:
            self._callback(None)

    def _on_motion(self, widget, event):
        if self._dragging:
            self._cur_x = int(event.x)
            self._cur_y = int(event.y)
            self._win.queue_draw()

    def _on_key(self, widget, event):
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk
        if event.keyval == Gdk.KEY_Escape:
            self._win.destroy()
            self._callback(None)


class _GtkStopButton:
    """Floating red circle stop button that appears during recording (GTK3)."""

    def __init__(self, on_stop: Callable[[], None]):
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        self._on_stop = on_stop

        self._win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self._win.set_title("Stop Recording")
        self._win.set_decorated(False)
        self._win.set_app_paintable(True)
        self._win.set_keep_above(True)
        self._win.set_default_size(48, 48)
        self._win.set_resizable(False)
        self._win.set_skip_taskbar_hint(True)
        self._win.set_skip_pager_hint(True)

        screen = self._win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._win.set_visual(visual)

        sw, _ = _get_screen_size()
        self._win.move(sw - 70, 20)

        self._win.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self._win.connect("draw", self._on_draw)
        self._win.connect("button-press-event", self._on_click)
        self._win.connect("enter-notify-event", self._on_enter)
        self._win.connect("leave-notify-event", self._on_leave)

        self._hover = False

        cursor = Gdk.Cursor.new_from_name(self._win.get_display(), "pointer")
        self._win.show_all()
        self._win.get_window().set_cursor(cursor)

        # Pulse animation
        self._pulse_alpha = 1.0
        self._pulse_dir = -1
        from gi.repository import GLib
        GLib.timeout_add(50, self._pulse_tick)

    def _pulse_tick(self):
        self._pulse_alpha += self._pulse_dir * 0.04
        if self._pulse_alpha <= 0.5:
            self._pulse_dir = 1
        elif self._pulse_alpha >= 1.0:
            self._pulse_dir = -1
        try:
            self._win.queue_draw()
        except Exception:
            return False
        return True  # keep ticking

    def _on_draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(0)  # CLEAR
        cr.paint()

        import cairo
        cr.set_operator(cairo.OPERATOR_OVER)

        # Red circle with pulse
        r = 0.85 if self._hover else 0.75
        cr.set_source_rgba(0.9, 0.1, 0.1, self._pulse_alpha)
        cr.arc(24, 24, 20, 0, 2 * 3.14159)
        cr.fill()

        # White square (stop icon) in center
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.rectangle(16, 16, 16, 16)
        cr.fill()

    def _on_click(self, widget, event):
        self.destroy()
        self._on_stop()

    def _on_enter(self, widget, event):
        self._hover = True
        self._win.queue_draw()

    def _on_leave(self, widget, event):
        self._hover = False
        self._win.queue_draw()

    def destroy(self):
        try:
            self._win.destroy()
        except Exception:
            pass


class _GtkCaptureToolbar:
    """Floating capture toolbar with mode switchers and action buttons (GTK3)."""

    def __init__(
        self,
        on_screenshot: Callable[[str, CaptureRegion | None], None],
        on_record: Callable[[str, CaptureRegion | None], None],
    ):
        """
        Args:
            on_screenshot: Called with (mode, region_or_none) when screenshot is triggered.
            on_record: Called with (mode, region_or_none) when record is triggered.
        """
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk

        self._on_screenshot = on_screenshot
        self._on_record = on_record
        self._mode = MODE_FULLSCREEN

        self._win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self._win.set_title("H4KShot")
        self._win.set_decorated(False)
        self._win.set_app_paintable(True)
        self._win.set_keep_above(True)
        self._win.set_resizable(False)
        self._win.set_skip_taskbar_hint(True)

        screen = self._win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self._win.set_visual(visual)

        self._win.connect("draw", self._draw_bg)
        self._win.connect("key-press-event", self._on_key)
        self._win.add_events(Gdk.EventMask.KEY_PRESS_MASK)

        # --- Layout ---
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)

        # Mode buttons (left side)
        self._btn_area = self._mode_button("⬒  Area", MODE_AREA)
        self._btn_full = self._mode_button("🖥  Full Screen", MODE_FULLSCREEN)
        self._btn_window = self._mode_button("◻  Window", MODE_WINDOW)

        hbox.pack_start(self._btn_area, False, False, 0)
        hbox.pack_start(self._btn_full, False, False, 0)
        hbox.pack_start(self._btn_window, False, False, 0)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(sep, False, False, 6)

        # Screenshot button (white circle)
        btn_ss = Gtk.Button()
        btn_ss.set_relief(Gtk.ReliefStyle.NONE)
        btn_ss.set_tooltip_text("Take Screenshot")
        ss_drawing = Gtk.DrawingArea()
        ss_drawing.set_size_request(36, 36)
        ss_drawing.connect("draw", self._draw_screenshot_btn)
        btn_ss.add(ss_drawing)
        btn_ss.connect("clicked", lambda _: self._do_screenshot())
        hbox.pack_start(btn_ss, False, False, 0)

        # Record button (red circle)
        btn_rec = Gtk.Button()
        btn_rec.set_relief(Gtk.ReliefStyle.NONE)
        btn_rec.set_tooltip_text("Start Recording")
        rec_drawing = Gtk.DrawingArea()
        rec_drawing.set_size_request(36, 36)
        rec_drawing.connect("draw", self._draw_record_btn)
        btn_rec.add(rec_drawing)
        btn_rec.connect("clicked", lambda _: self._do_record())
        hbox.pack_start(btn_rec, False, False, 0)

        # Close button
        btn_close = Gtk.Button(label="✕")
        btn_close.set_relief(Gtk.ReliefStyle.NONE)
        btn_close.set_tooltip_text("Close")
        btn_close.connect("clicked", lambda _: self._win.destroy())
        hbox.pack_end(btn_close, False, False, 0)

        self._win.add(hbox)

        # Center on screen
        sw, sh = _get_screen_size()
        self._win.show_all()
        alloc = self._win.get_allocation()
        self._win.move((sw - alloc.width) // 2, sh - alloc.height - 60)

        self._update_mode_buttons()

    def _mode_button(self, label: str, mode: str):
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        btn = Gtk.ToggleButton(label=label)
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn._h4k_mode = mode  # stash mode on the widget
        btn.connect("toggled", self._on_mode_toggled)
        return btn

    def _on_mode_toggled(self, btn):
        if btn.get_active():
            self._set_mode(btn._h4k_mode)

    def _set_mode(self, mode: str):
        self._mode = mode
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        for btn, m in [
            (self._btn_area, MODE_AREA),
            (self._btn_full, MODE_FULLSCREEN),
            (self._btn_window, MODE_WINDOW),
        ]:
            # Temporarily block the toggled signal to avoid recursive calls
            btn.handler_block_by_func(self._on_mode_toggled)
            btn.set_active(m == self._mode)
            btn.handler_unblock_by_func(self._on_mode_toggled)

    @staticmethod
    def _draw_bg(widget, cr):
        import cairo
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0.15, 0.15, 0.15, 0.92)
        _rounded_rect(cr, 0, 0, widget.get_allocated_width(), widget.get_allocated_height(), 12)
        cr.fill()

    @staticmethod
    def _draw_screenshot_btn(widget, cr):
        """White filled circle – screenshot button."""
        import cairo
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        # Outer ring
        cr.set_source_rgba(0.9, 0.9, 0.9, 1)
        cr.arc(w / 2, h / 2, 14, 0, 2 * 3.14159)
        cr.set_line_width(2.5)
        cr.stroke()
        # Inner fill
        cr.set_source_rgba(1, 1, 1, 1)
        cr.arc(w / 2, h / 2, 10, 0, 2 * 3.14159)
        cr.fill()

    @staticmethod
    def _draw_record_btn(widget, cr):
        """Red filled circle – record button."""
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        # Outer ring
        cr.set_source_rgba(0.8, 0.2, 0.2, 1)
        cr.arc(w / 2, h / 2, 14, 0, 2 * 3.14159)
        cr.set_line_width(2.5)
        cr.stroke()
        # Inner fill
        cr.set_source_rgba(0.9, 0.15, 0.15, 1)
        cr.arc(w / 2, h / 2, 10, 0, 2 * 3.14159)
        cr.fill()

    def _on_key(self, widget, event):
        _ensure_gi()
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk
        if event.keyval == Gdk.KEY_Escape:
            self._win.destroy()

    def _do_screenshot(self):
        self._win.hide()
        self._resolve_region(lambda region: self._on_screenshot(self._mode, region))

    def _do_record(self):
        self._win.hide()
        self._resolve_region(lambda region: self._on_record(self._mode, region))

    def _resolve_region(self, callback: Callable[[CaptureRegion | None], None]):
        """Resolve the region based on the current mode, then call callback."""
        if self._mode == MODE_FULLSCREEN:
            callback(None)
            self._win.destroy()
        elif self._mode == MODE_WINDOW:
            region = _get_active_window_geometry()
            callback(region)
            self._win.destroy()
        elif self._mode == MODE_AREA:
            # Brief delay to let the toolbar fade, then show selection overlay
            _ensure_gi()
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import GLib

            def _show_selector():
                _GtkRegionSelector(lambda r: (callback(r), self._win.destroy()))
                return False

            GLib.timeout_add(200, _show_selector)

    def destroy(self):
        try:
            self._win.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tkinter fallback (macOS / Windows)
# ---------------------------------------------------------------------------

class _TkRegionSelector:
    """Full-screen transparent overlay for click-drag region selection (Tkinter)."""

    def __init__(self, callback: Callable[[CaptureRegion | None], None]):
        import tkinter as tk

        self._callback = callback
        self._start_x = self._start_y = 0

        self._root = tk.Tk()
        self._root.attributes("-fullscreen", True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.3)
        self._root.configure(background="black")
        self._root.config(cursor="crosshair")

        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._rect_id = None

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._root.bind("<Escape>", lambda e: self._cancel())

        self._root.mainloop()

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#4488ff", width=2
        )

    def _on_motion(self, event):
        if self._rect_id:
            self._canvas.coords(self._rect_id, self._start_x, self._start_y, event.x, event.y)

    def _on_release(self, event):
        x = min(self._start_x, event.x)
        y = min(self._start_y, event.y)
        w = abs(event.x - self._start_x)
        h = abs(event.y - self._start_y)
        self._root.destroy()
        if w > 5 and h > 5:
            self._callback(CaptureRegion(int(x), int(y), int(w), int(h)))
        else:
            self._callback(None)

    def _cancel(self):
        self._root.destroy()
        self._callback(None)


class _TkStopButton:
    """Floating red stop button (Tkinter)."""

    def __init__(self, on_stop: Callable[[], None]):
        import tkinter as tk

        self._on_stop = on_stop
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)

        sw = self._root.winfo_screenwidth()
        self._root.geometry(f"48x48+{sw - 70}+20")

        try:
            self._root.attributes("-transparentcolor", "magenta")
            self._root.configure(bg="magenta")
            bg = "magenta"
        except Exception:
            bg = "black"
            self._root.configure(bg=bg)

        canvas = tk.Canvas(self._root, width=48, height=48, bg=bg,
                           highlightthickness=0, bd=0)
        canvas.pack()

        # Red circle
        canvas.create_oval(4, 4, 44, 44, fill="#e01515", outline="#cc1111", width=2)
        # White stop square
        canvas.create_rectangle(16, 16, 32, 32, fill="white", outline="white")

        canvas.bind("<Button-1>", lambda e: self._stop())
        self._root.bind("<Button-1>", lambda e: self._stop())

        # Run in non-blocking mode (no mainloop – we just update it)
        self._destroyed = False
        self._update()

    def _update(self):
        if not self._destroyed:
            try:
                self._root.update_idletasks()
                self._root.update()
                self._root.after(50, self._update)
            except Exception:
                pass

    def _stop(self):
        self.destroy()
        self._on_stop()

    def destroy(self):
        self._destroyed = True
        try:
            self._root.destroy()
        except Exception:
            pass


class _TkCaptureToolbar:
    """Floating capture toolbar (Tkinter – macOS/Windows)."""

    def __init__(
        self,
        on_screenshot: Callable[[str, CaptureRegion | None], None],
        on_record: Callable[[str, CaptureRegion | None], None],
    ):
        import tkinter as tk

        self._on_screenshot = on_screenshot
        self._on_record = on_record
        self._mode = MODE_FULLSCREEN

        self._root = tk.Tk()
        self._root.title("H4KShot")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.configure(bg="#262626")

        frame = tk.Frame(self._root, bg="#262626", padx=10, pady=8)
        frame.pack()

        # Mode buttons
        self._mode_var = tk.StringVar(value=MODE_FULLSCREEN)
        modes = [("⬒ Area", MODE_AREA), ("🖥 Full", MODE_FULLSCREEN), ("◻ Window", MODE_WINDOW)]
        for label, mode in modes:
            rb = tk.Radiobutton(
                frame, text=label, variable=self._mode_var, value=mode,
                indicatoron=False, bg="#444", fg="white", selectcolor="#666",
                activebackground="#555", activeforeground="white",
                relief="flat", padx=8, pady=4,
                command=lambda m=mode: self._set_mode(m),
            )
            rb.pack(side="left", padx=2)

        # Separator
        sep = tk.Frame(frame, width=2, bg="#555", height=28)
        sep.pack(side="left", padx=8, fill="y")

        # Screenshot button (white circle)
        ss_canvas = tk.Canvas(frame, width=36, height=36, bg="#262626",
                              highlightthickness=0, bd=0)
        ss_canvas.create_oval(4, 4, 32, 32, outline="#ddd", width=2)
        ss_canvas.create_oval(8, 8, 28, 28, fill="white", outline="white")
        ss_canvas.pack(side="left", padx=4)
        ss_canvas.bind("<Button-1>", lambda e: self._do_screenshot())

        # Record button (red circle)
        rec_canvas = tk.Canvas(frame, width=36, height=36, bg="#262626",
                               highlightthickness=0, bd=0)
        rec_canvas.create_oval(4, 4, 32, 32, outline="#cc3333", width=2)
        rec_canvas.create_oval(8, 8, 28, 28, fill="#e01515", outline="#e01515")
        rec_canvas.pack(side="left", padx=4)
        rec_canvas.bind("<Button-1>", lambda e: self._do_record())

        # Close button
        close_btn = tk.Button(
            frame, text="✕", bg="#262626", fg="#aaa",
            activebackground="#444", activeforeground="white",
            relief="flat", bd=0, command=self._root.destroy,
        )
        close_btn.pack(side="left", padx=(8, 0))

        # Center on screen
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        ww = self._root.winfo_width()
        wh = self._root.winfo_height()
        self._root.geometry(f"+{(sw - ww) // 2}+{sh - wh - 60}")

        self._root.bind("<Escape>", lambda e: self._root.destroy())
        self._root.mainloop()

    def _set_mode(self, mode):
        self._mode = mode

    def _do_screenshot(self):
        mode = self._mode
        self._root.withdraw()
        self._resolve_region(mode, lambda region: self._on_screenshot(mode, region))

    def _do_record(self):
        mode = self._mode
        self._root.withdraw()
        self._resolve_region(mode, lambda region: self._on_record(mode, region))

    def _resolve_region(self, mode: str, callback: Callable[[CaptureRegion | None], None]):
        if mode == MODE_FULLSCREEN:
            callback(None)
            self._root.destroy()
        elif mode == MODE_WINDOW:
            region = _get_active_window_geometry()
            callback(region)
            self._root.destroy()
        elif mode == MODE_AREA:
            self._root.destroy()
            import time
            time.sleep(0.2)
            _TkRegionSelector(callback)

    def destroy(self):
        try:
            self._root.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API (auto-selects backend)
# ---------------------------------------------------------------------------

def show_capture_toolbar(
    on_screenshot: Callable[[str, CaptureRegion | None], None],
    on_record: Callable[[str, CaptureRegion | None], None],
) -> None:
    """Show the capture toolbar overlay.

    Args:
        on_screenshot: Called with (mode, region_or_none).
        on_record: Called with (mode, region_or_none).
    """
    system = platform.system()
    if system == "Linux" and _gtk_available():
        _GtkCaptureToolbar(on_screenshot, on_record)
    else:
        _TkCaptureToolbar(on_screenshot, on_record)


def show_region_selector(callback: Callable[[CaptureRegion | None], None]) -> None:
    """Show a full-screen region selector overlay."""
    system = platform.system()
    if system == "Linux" and _gtk_available():
        _GtkRegionSelector(callback)
    else:
        _TkRegionSelector(callback)


def show_stop_button(on_stop: Callable[[], None]) -> object:
    """Show a floating red stop button. Returns an object with a .destroy() method."""
    system = platform.system()
    if system == "Linux" and _gtk_available():
        return _GtkStopButton(on_stop)
    else:
        return _TkStopButton(on_stop)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _rounded_rect(cr, x, y, w, h, r):
    """Draw a rounded rectangle path (cairo)."""
    import math
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
