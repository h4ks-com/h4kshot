"""Cross-platform clipboard helpers."""

from __future__ import annotations

import platform
import subprocess
import shutil


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard.

    Returns True on success, False on failure.
    """
    system = platform.system()

    try:
        if system == "Darwin":
            subprocess.run(
                ["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5
            )
            return True

        elif system == "Windows":
            # Use clip.exe which ships with Windows
            subprocess.run(
                ["clip.exe"], input=text.encode("utf-16le"), check=True, timeout=5
            )
            return True

        else:
            # Linux – try xclip, then xsel, then wl-copy (Wayland)
            if shutil.which("xclip"):
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=5,
                )
                return True
            elif shutil.which("xsel"):
                subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=5,
                )
                return True
            elif shutil.which("wl-copy"):
                subprocess.run(
                    ["wl-copy", text],
                    check=True,
                    timeout=5,
                )
                return True
            else:
                # Fallback to pyperclip
                import pyperclip
                pyperclip.copy(text)
                return True

    except Exception:
        # Last-resort fallback
        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except Exception:
            return False
