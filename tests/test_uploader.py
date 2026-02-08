"""Tests for the uploader module, including live integration tests against s.h4ks.com."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import responses

from h4kshot.uploader import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    UPLOAD_URL,
    UploadResult,
    check_file_size,
    upload_file,
)


# ------------------------------------------------------------------ #
# Unit tests (mocked HTTP)
# ------------------------------------------------------------------ #

class TestUploadFileMocked:
    """Unit tests with mocked HTTP responses."""

    @responses.activate
    def test_successful_upload(self, tmp_path):
        responses.add(
            responses.POST,
            UPLOAD_URL,
            json={"status": "success", "url": "https://s.h4ks.com/abc.png"},
            status=200,
        )
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG" + b"\x00" * 100)

        result = upload_file(f)
        assert result.success is True
        assert result.url == "https://s.h4ks.com/abc.png"

    @responses.activate
    def test_server_error_response(self, tmp_path):
        responses.add(
            responses.POST,
            UPLOAD_URL,
            json={"status": "error", "message": "File too large"},
            status=200,
        )
        f = tmp_path / "test.png"
        f.write_bytes(b"\x00" * 100)

        result = upload_file(f)
        assert result.success is False
        assert "too large" in result.error.lower()

    def test_file_not_found(self):
        result = upload_file("/nonexistent/file.png")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.png"
        f.write_bytes(b"")
        result = upload_file(f)
        assert result.success is False
        assert "empty" in result.error.lower()

    def test_file_too_large(self, tmp_path):
        f = tmp_path / "huge.bin"
        # Create a sparse-like large file by writing just enough to exceed the limit
        with open(f, "wb") as fh:
            fh.seek(MAX_FILE_SIZE_BYTES + 1)
            fh.write(b"\x00")

        result = upload_file(f)
        assert result.success is False
        assert "too large" in result.error.lower()

    @responses.activate
    def test_connection_error(self, tmp_path):
        import requests as req
        responses.add(
            responses.POST,
            UPLOAD_URL,
            body=req.exceptions.ConnectionError("Network unreachable"),
        )
        f = tmp_path / "test.png"
        f.write_bytes(b"\x00" * 100)

        result = upload_file(f)
        assert result.success is False

    @responses.activate
    def test_timeout(self, tmp_path):
        import requests as req
        responses.add(
            responses.POST,
            UPLOAD_URL,
            body=req.exceptions.Timeout("timed out"),
        )
        f = tmp_path / "test.png"
        f.write_bytes(b"\x00" * 100)

        result = upload_file(f)
        assert result.success is False
        assert "timed out" in result.error.lower()


class TestCheckFileSize:
    def test_within_limit(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_bytes(b"hello")
        assert check_file_size(f) is True

    def test_exceeds_limit(self, tmp_path):
        f = tmp_path / "huge.bin"
        with open(f, "wb") as fh:
            fh.seek(MAX_FILE_SIZE_BYTES + 1)
            fh.write(b"\x00")
        assert check_file_size(f) is False

    def test_nonexistent(self):
        assert check_file_size("/no/such/file") is False


# ------------------------------------------------------------------ #
# Live integration test against s.h4ks.com
# ------------------------------------------------------------------ #

class TestLiveUpload:
    """Integration tests that actually call s.h4ks.com.

    These are marked with the 'integration' marker so they can be
    skipped in offline environments:  pytest -m 'not integration'
    """

    @pytest.mark.integration
    def test_upload_small_text_file(self, tmp_path):
        """Upload a small text file to s.h4ks.com and verify we get a URL back."""
        f = tmp_path / "h4kshot_test.txt"
        f.write_text("h4kshot integration test file – safe to delete", encoding="utf-8")

        result = upload_file(f)
        assert result.success is True, f"Upload failed: {result.error}"
        assert result.url is not None
        assert "h4ks.com" in result.url

    @pytest.mark.integration
    def test_upload_small_png(self, tmp_path):
        """Upload a tiny PNG to s.h4ks.com."""
        # Minimal valid 1x1 red PNG
        from PIL import Image

        f = tmp_path / "h4kshot_test.png"
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        img.save(str(f), "PNG")

        result = upload_file(f)
        assert result.success is True, f"Upload failed: {result.error}"
        assert result.url is not None
        assert result.url.endswith(".png")

    @pytest.mark.integration
    def test_uploaded_file_is_accessible(self, tmp_path):
        """Upload a file and verify the returned URL is reachable."""
        import requests

        f = tmp_path / "h4kshot_access_test.txt"
        f.write_text("h4kshot access test", encoding="utf-8")

        result = upload_file(f)
        assert result.success is True, f"Upload failed: {result.error}"

        # The URL should be reachable
        resp = requests.get(result.url, timeout=15)
        assert resp.status_code == 200
        assert "h4kshot access test" in resp.text
