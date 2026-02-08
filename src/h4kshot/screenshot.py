"""Cross-platform screenshot capture."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import mss
import mss.tools
from PIL import Image


def capture_screenshot(output_path: str | Path | None = None, monitor: int = 0) -> Path:
    """Capture a screenshot of the entire screen (or a specific monitor).

    Args:
        output_path: Where to save the PNG. If None, a temp file is created.
        monitor: Monitor index (0 = all monitors combined, 1 = first, etc.).

    Returns:
        Path to the saved PNG file.
    """
    if output_path is None:
        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="h4kshot_")
        import os
        os.close(fd)
        output_path = Path(tmp)
    else:
        output_path = Path(output_path)

    with mss.mss() as sct:
        # monitor=0 means all monitors combined
        mon = sct.monitors[monitor]
        screenshot = sct.grab(mon)

        # Convert to PIL Image and save as optimized PNG
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.save(str(output_path), "PNG", optimize=True)

    return output_path


def capture_region(
    left: int, top: int, width: int, height: int, output_path: str | Path | None = None
) -> Path:
    """Capture a specific region of the screen.

    Args:
        left: X coordinate of the top-left corner.
        top: Y coordinate of the top-left corner.
        width: Width of the region.
        height: Height of the region.
        output_path: Where to save the PNG. If None, a temp file is created.

    Returns:
        Path to the saved PNG file.
    """
    if output_path is None:
        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="h4kshot_")
        import os
        os.close(fd)
        output_path = Path(tmp)
    else:
        output_path = Path(output_path)

    region = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        screenshot = sct.grab(region)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.save(str(output_path), "PNG", optimize=True)

    return output_path
