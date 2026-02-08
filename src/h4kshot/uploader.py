"""Upload files to s.h4ks.com."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

UPLOAD_URL = "https://s.h4ks.com/api/"
MAX_FILE_SIZE_MB = 64
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@dataclass
class UploadResult:
    """Result of an upload operation."""

    success: bool
    url: str | None = None
    error: str | None = None


def upload_file(file_path: str | Path, upload_url: str = UPLOAD_URL, timeout: int = 120) -> UploadResult:
    """Upload a file to the h4ks file sharing service.

    Args:
        file_path: Path to the file to upload.
        upload_url: Base URL of the upload service.
        timeout: Request timeout in seconds.

    Returns:
        UploadResult with success status and url or error message.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return UploadResult(success=False, error=f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        return UploadResult(
            success=False,
            error=f"File too large: {file_size / (1024 * 1024):.1f} MB exceeds {MAX_FILE_SIZE_MB} MB limit",
        )

    if file_size == 0:
        return UploadResult(success=False, error="File is empty")

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            response = requests.post(upload_url, files=files, timeout=timeout)

        response.raise_for_status()
        data = response.json()

        if data.get("status") == "success":
            return UploadResult(success=True, url=data.get("url"))
        else:
            return UploadResult(success=False, error=data.get("message", "Unknown error"))

    except requests.exceptions.Timeout:
        return UploadResult(success=False, error="Upload timed out")
    except requests.exceptions.ConnectionError:
        return UploadResult(success=False, error="Connection failed – is the network available?")
    except requests.exceptions.RequestException as e:
        return UploadResult(success=False, error=f"Upload failed: {e}")
    except (ValueError, KeyError) as e:
        return UploadResult(success=False, error=f"Invalid response from server: {e}")


def check_file_size(file_path: str | Path) -> bool:
    """Check whether a file is within the upload size limit.

    Returns True if the file can be uploaded.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return False
    return file_path.stat().st_size <= MAX_FILE_SIZE_BYTES
