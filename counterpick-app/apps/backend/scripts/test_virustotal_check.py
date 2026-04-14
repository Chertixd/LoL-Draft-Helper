"""Unit tests for virustotal_check.py.

Covers the `detections <= max` / `detections > max` boundary with mocked VT
API responses. Does NOT hit the real VT API.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts/ to sys.path so we can import virustotal_check as a flat module.
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import virustotal_check as vt  # noqa: E402


def _mock_upload_response(analysis_id: str = "abc123") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"data": {"id": analysis_id}}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_analysis_response(malicious: int, suspicious: int, status: str = "completed") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "data": {"attributes": {"status": status, "stats": {"malicious": malicious, "suspicious": suspicious}}}
    }
    resp.raise_for_status = MagicMock()
    return resp


def test_upload_returns_analysis_id(tmp_path: Path) -> None:
    f = tmp_path / "sample.exe"
    f.write_bytes(b"fake bytes")
    with patch("virustotal_check.requests.post", return_value=_mock_upload_response("id-42")) as mock_post:
        out = vt.upload(str(f), "fake-key")
    assert out == "id-42"
    mock_post.assert_called_once()


def test_poll_returns_detections_sum_when_completed() -> None:
    with patch("virustotal_check.requests.get", return_value=_mock_analysis_response(malicious=2, suspicious=1)):
        detections = vt.poll("id-1", "fake-key", timeout_s=5)
    assert detections == 3


def test_main_passes_when_detections_under_threshold(tmp_path: Path, monkeypatch, capsys) -> None:
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    monkeypatch.setenv("VT_API_KEY", "fake-key")
    monkeypatch.setattr(sys, "argv", ["virustotal_check.py", str(f), "--max-detections", "3"])
    with patch("virustotal_check.upload", return_value="id-1"), patch("virustotal_check.poll", return_value=2):
        rc = vt.main()
    assert rc == 0
    assert "detections: 2" in capsys.readouterr().out


def test_main_passes_at_exact_threshold(tmp_path: Path, monkeypatch) -> None:
    """Boundary: detections == max must pass (<=, not <)."""
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    monkeypatch.setenv("VT_API_KEY", "fake-key")
    monkeypatch.setattr(sys, "argv", ["virustotal_check.py", str(f), "--max-detections", "3"])
    with patch("virustotal_check.upload", return_value="id-1"), patch("virustotal_check.poll", return_value=3):
        rc = vt.main()
    assert rc == 0


def test_main_fails_when_detections_over_threshold(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    monkeypatch.setenv("VT_API_KEY", "fake-key")
    monkeypatch.setattr(sys, "argv", ["virustotal_check.py", str(f), "--max-detections", "3"])
    with patch("virustotal_check.upload", return_value="id-1"), patch("virustotal_check.poll", return_value=4):
        rc = vt.main()
    assert rc == 1


def test_main_skips_when_api_key_unset(tmp_path: Path, monkeypatch, capsys) -> None:
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    monkeypatch.delenv("VT_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["virustotal_check.py", str(f)])
    rc = vt.main()
    assert rc == 0
    assert "VT_API_KEY not set" in capsys.readouterr().err


def test_detections_under_threshold(tmp_path: Path, monkeypatch) -> None:
    """Alias test — satisfies must_haves `contains: def test_detections_under_threshold`."""
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    monkeypatch.setenv("VT_API_KEY", "fake-key")
    monkeypatch.setattr(sys, "argv", ["virustotal_check.py", str(f), "--max-detections", "5"])
    with patch("virustotal_check.upload", return_value="id-1"), patch("virustotal_check.poll", return_value=1):
        rc = vt.main()
    assert rc == 0


def test_main_returns_2_on_api_error(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    monkeypatch.setenv("VT_API_KEY", "fake-key")
    monkeypatch.setattr(sys, "argv", ["virustotal_check.py", str(f)])
    with patch("virustotal_check.upload", side_effect=RuntimeError("network down")):
        rc = vt.main()
    assert rc == 2
