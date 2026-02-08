"""Cross-platform screen recording with ffmpeg and automatic size-limit cutoff."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from h4kshot.uploader import MAX_FILE_SIZE_BYTES

# Leave a 1 MB margin so we don't exceed the server limit
SIZE_LIMIT_BYTES = MAX_FILE_SIZE_BYTES - 1 * 1024 * 1024  # 63 MB


def _get_ffmpeg() -> str:
    """Return the path to ffmpeg or raise if not installed."""
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError(
            "ffmpeg is not installed or not on PATH. "
            "Please install ffmpeg to use screen recording."
        )
    return path


def _build_ffmpeg_cmd(output_path: str, framerate: int = 30) -> list[str]:
    """Build the ffmpeg command for screen capture on the current platform."""
    ffmpeg = _get_ffmpeg()
    system = platform.system()

    if system == "Linux":
        display = os.environ.get("DISPLAY", ":0")
        return [
            ffmpeg, "-y",
            "-f", "x11grab",
            "-framerate", str(framerate),
            "-i", display,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    elif system == "Darwin":
        # macOS: use avfoundation, device 1 is screen
        return [
            ffmpeg, "-y",
            "-f", "avfoundation",
            "-framerate", str(framerate),
            "-i", "1:none",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    elif system == "Windows":
        return [
            ffmpeg, "-y",
            "-f", "gdigrab",
            "-framerate", str(framerate),
            "-i", "desktop",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    else:
        raise RuntimeError(f"Unsupported platform for recording: {system}")


class ScreenRecorder:
    """Manages an ffmpeg screen recording process with auto size-limit cutoff."""

    def __init__(self, output_path: str | Path | None = None, framerate: int = 30):
        if output_path is None:
            fd, tmp = tempfile.mkstemp(suffix=".mp4", prefix="h4kshot_rec_")
            os.close(fd)
            self.output_path = Path(tmp)
        else:
            self.output_path = Path(output_path)

        self.framerate = framerate
        self._process: subprocess.Popen | None = None
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._auto_stopped = False

    @property
    def is_recording(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def auto_stopped(self) -> bool:
        """True if recording was automatically stopped due to size limit."""
        return self._auto_stopped

    def start(self) -> None:
        """Start screen recording."""
        if self.is_recording:
            return

        cmd = _build_ffmpeg_cmd(str(self.output_path), self.framerate)
        # Suppress ffmpeg output; send 'q' to stdin to stop gracefully
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._stop_event.clear()
        self._auto_stopped = False
        self._monitor_thread = threading.Thread(target=self._monitor_size, daemon=True)
        self._monitor_thread.start()

    def stop(self) -> Path:
        """Stop recording and return the path to the output file."""
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            try:
                # Send 'q' to ffmpeg to stop gracefully
                self._process.stdin.write(b"q")
                self._process.stdin.flush()
                self._process.wait(timeout=10)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
        self._process = None
        return self.output_path

    def _monitor_size(self) -> None:
        """Background thread: watch output file size and auto-stop if near limit."""
        while not self._stop_event.is_set():
            time.sleep(0.5)
            try:
                if self.output_path.exists():
                    size = self.output_path.stat().st_size
                    if size >= SIZE_LIMIT_BYTES:
                        self._auto_stopped = True
                        self.stop()
                        return
            except OSError:
                pass
