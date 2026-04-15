"""CDN-02..CDN-04 verification: cache lifecycle without network.

RED phase — tests fail until 02-01 Task 2 lands ``json_repo.py``.

These tests cover the mocked-HTTP cache lifecycle for
``lolalytics_api.json_repo`` (Phase 2 CDN data plane). No network is touched;
``requests.get`` is stubbed with ``unittest.mock.patch`` so each test runs
deterministically on ``windows-latest`` / Python 3.12.

Requirements exercised:
- CDN-02: cache layout (``<table>.json`` + ``<table>.meta.json`` pair under
  ``user_cache_dir()/cdn/``, atomic write, schema_version enforcement).
- CDN-03: conditional GET (ETag / If-None-Match + Last-Modified /
  If-Modified-Since; 304 reuses cached body).
- CDN-04: corrupt-cache recovery (JSONDecodeError → delete pair + refetch;
  unreachable CDN with cache → stale flag).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# NOTE: This import currently fails — that is the RED-phase proof.
# Task 2 lands ``json_repo.py`` and flips the file to GREEN.
from lolalytics_api import json_repo


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point ``json_repo._cache_dir`` at a ``tmp_path`` so each test is fresh.

    Also resets the module-level ``_stale_state`` and ``_data`` dicts so test
    order cannot leak state across cases.
    """
    cdn_dir = tmp_path / "cdn"
    cdn_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "lolalytics_api.json_repo._cache_dir",
        lambda: cdn_dir,
    )
    # Reset module-level state — otherwise a 304-test preloading cache would
    # see stale data from a prior 200-test in the same session.
    if hasattr(json_repo, "_stale_state"):
        json_repo._stale_state.clear()
    if hasattr(json_repo, "_data"):
        json_repo._data.clear()
    yield cdn_dir


def _make_resp(status: int, body: dict | None = None, headers: dict | None = None):
    """Build a ``requests.Response``-shaped MagicMock."""
    m = MagicMock()
    m.status_code = status
    m.headers = headers or {}
    m.content = json.dumps(body).encode("utf-8") if body is not None else b""
    m.text = json.dumps(body) if body is not None else ""
    m.json.return_value = body
    return m


def _canonical_sha256(rows: list) -> str:
    """Match json_repo's canonical form exactly (sort_keys + compact separators)."""
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cache_cold_fetch_writes_pair(isolated_cache):
    """200 path writes both ``<table>.json`` and ``<table>.meta.json`` atomically."""
    body = {
        "__meta": {
            "exported_at": "2026-04-14T03:15:00Z",
            "sha256": "irrelevant_test",
            "row_count": 0,
            "schema_version": 1,
        },
        "rows": [],
    }
    headers = {
        "ETag": 'W/"abc123"',
        "Last-Modified": "Mon, 14 Apr 2026 03:15:00 GMT",
        "Date": "Mon, 14 Apr 2026 03:15:05 GMT",
    }
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(200, body, headers),
    ):
        # Bypass the real sha256 check — covered separately in
        # test_sha256_mismatch_raises_cdnerror.
        with patch("lolalytics_api.json_repo.hashlib.sha256") as m:
            m.return_value.hexdigest.return_value = "irrelevant_test"
            rows = json_repo._fetch_one("items")

    assert rows == []
    assert (isolated_cache / "items.json").exists()
    assert (isolated_cache / "items.meta.json").exists()
    meta = json.loads((isolated_cache / "items.meta.json").read_text(encoding="utf-8"))
    assert meta["etag"] == 'W/"abc123"'
    assert meta["last_modified"] == "Mon, 14 Apr 2026 03:15:00 GMT"


def test_cache_304_reuses_cached_body(isolated_cache):
    """304 path reads ``<table>.json`` and skips any disk write."""
    cached = {"__meta": {"schema_version": 1}, "rows": [{"id": 1}]}
    (isolated_cache / "items.json").write_text(
        json.dumps(cached), encoding="utf-8"
    )
    (isolated_cache / "items.meta.json").write_text(
        json.dumps(
            {
                "etag": 'W/"old"',
                "last_modified": "Mon, 13 Apr 2026 00:00:00 GMT",
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(304, headers={"ETag": 'W/"old"'}),
    ) as get:
        rows = json_repo._fetch_one("items")

    assert rows == [{"id": 1}]
    sent = get.call_args.kwargs["headers"]
    assert sent.get("If-None-Match") == 'W/"old"'
    assert sent.get("If-Modified-Since") == "Mon, 13 Apr 2026 00:00:00 GMT"


def test_corrupt_cache_recovers(isolated_cache):
    """JSONDecodeError on body → delete pair → refetch 200 — no exception surfaces."""
    (isolated_cache / "items.json").write_text("{ truncated...", encoding="utf-8")
    (isolated_cache / "items.meta.json").write_text(
        json.dumps({"etag": 'W/"stale"'}), encoding="utf-8"
    )
    body = {
        "__meta": {"schema_version": 1, "sha256": "x", "row_count": 0},
        "rows": [],
    }
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(200, body),
    ):
        with patch("lolalytics_api.json_repo.hashlib.sha256") as m:
            m.return_value.hexdigest.return_value = "x"
            rows = json_repo._fetch_one("items")

    # Refetched — no crash, rows match the 200 body.
    assert rows == []
    # Reading the body file again yields valid JSON (the corrupt content was replaced).
    reloaded = json.loads((isolated_cache / "items.json").read_text(encoding="utf-8"))
    assert reloaded["rows"] == []


def test_atomic_write_no_partial(isolated_cache):
    """``_atomic_write_json`` uses tmp + os.replace; no ``.tmp`` leftover."""
    target = isolated_cache / "items.json"
    json_repo._atomic_write_json(target, {"x": 1})
    assert target.exists()
    assert not target.with_suffix(target.suffix + ".tmp").exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}


def test_schema_version_rejected(isolated_cache):
    """``schema_version > 1`` triggers ``CDNError`` (D-05 forward-compat guard)."""
    body = {
        "__meta": {
            "exported_at": "2026-04-14T00:00:00Z",
            "sha256": "anything",
            "row_count": 0,
            "schema_version": 2,  # client supports ≤ 1
        },
        "rows": [],
    }
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(200, body),
    ):
        with pytest.raises(json_repo.CDNError, match="schema_version"):
            json_repo._fetch_one("items")


def test_sha256_mismatch_raises_cdnerror(isolated_cache):
    """Meta sha256 must match the canonical serialization of rows."""
    rows = [{"id": 1, "patch": "14.8"}]
    # Intentionally wrong sha256 — real canonical is computed below but we
    # hand a different digest to force the mismatch.
    wrong_digest = "0" * 64
    body = {
        "__meta": {
            "exported_at": "2026-04-14T00:00:00Z",
            "sha256": wrong_digest,
            "row_count": len(rows),
            "schema_version": 1,
        },
        "rows": rows,
    }
    # Sanity-check: the real canonical form is different from the wrong digest.
    actual_digest = _canonical_sha256(rows)
    assert actual_digest != wrong_digest
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(200, body),
    ):
        with pytest.raises(json_repo.CDNError, match="sha256"):
            json_repo._fetch_one("items")


def test_cdn_unreachable_with_cache_flags_stale(isolated_cache):
    """Network error with cached body → return cached rows + set stale flag."""
    cached = {"__meta": {"schema_version": 1}, "rows": [{"id": 42}]}
    (isolated_cache / "items.json").write_text(
        json.dumps(cached), encoding="utf-8"
    )
    (isolated_cache / "items.meta.json").write_text(
        json.dumps({"etag": 'W/"cached"'}), encoding="utf-8"
    )
    with patch(
        "lolalytics_api.json_repo.requests.get",
        side_effect=requests.ConnectionError("boom"),
    ):
        rows = json_repo._fetch_one("items")

    assert rows == [{"id": 42}]
    assert json_repo.stale_status().get("items") is True


def test_cdn_unreachable_no_cache_raises_cdnerror(isolated_cache):
    """Network error with empty cache → loud ``CDNError`` (Phase 3 wraps UX)."""
    # isolated_cache is empty — no pre-populated files.
    with patch(
        "lolalytics_api.json_repo.requests.get",
        side_effect=requests.ConnectionError("no network"),
    ):
        with pytest.raises(json_repo.CDNError):
            json_repo._fetch_one("items")


# ---------------------------------------------------------------------------
# Per-patch sharding (matchups/synergies) — URLs and cache keys must carry
# the ``_<patch>`` suffix so the client reads ``matchups_15.24.json`` from
# the CDN instead of the (missing, too-large) single-file ``matchups.json``.
# ---------------------------------------------------------------------------


def test_non_per_patch_table_uses_plain_url_and_key(isolated_cache):
    """``items`` is NOT per-patch → URL is ``.../items.json`` and cache
    key is ``items`` regardless of any patch argument."""
    body = {
        "__meta": {"schema_version": 1, "sha256": "x", "row_count": 0},
        "rows": [],
    }
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(200, body),
    ) as get:
        with patch("lolalytics_api.json_repo.hashlib.sha256") as m:
            m.return_value.hexdigest.return_value = "x"
            json_repo._fetch_one("items")

    called_url = get.call_args.args[0]
    assert called_url.endswith("/items.json"), (
        f"non-per-patch URL must be plain: {called_url}"
    )
    # Cache key must be plain ``items.*`` — NOT ``items_<anything>``.
    assert (isolated_cache / "items.json").exists()
    assert (isolated_cache / "items.meta.json").exists()
    assert not any(isolated_cache.glob("items_*.json"))


def test_per_patch_table_uses_patched_url_and_cache_key(isolated_cache):
    """``matchups`` IS per-patch → URL is ``.../matchups_<patch>.json``
    and cache key is ``matchups_<patch>``."""
    patch_id = "15.24"
    body = {
        "__meta": {"schema_version": 1, "sha256": "x", "row_count": 0},
        "rows": [],
    }
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(200, body),
    ) as get:
        with patch("lolalytics_api.json_repo.hashlib.sha256") as m:
            m.return_value.hexdigest.return_value = "x"
            json_repo._fetch_one("matchups", patch_id)

    called_url = get.call_args.args[0]
    assert called_url.endswith(f"/matchups_{patch_id}.json"), (
        f"per-patch URL must carry _<patch> suffix: {called_url}"
    )
    # Cache key is ``matchups_<patch>``; the plain key MUST NOT appear.
    assert (isolated_cache / f"matchups_{patch_id}.json").exists()
    assert (isolated_cache / f"matchups_{patch_id}.meta.json").exists()
    assert not (isolated_cache / "matchups.json").exists()
    assert not (isolated_cache / "matchups.meta.json").exists()


def test_per_patch_table_without_patch_raises(isolated_cache):
    """Calling ``_fetch_one('matchups')`` without a patch is a programming
    error — raise ``ValueError`` rather than 404 at the CDN."""
    with pytest.raises(ValueError, match="patch"):
        json_repo._fetch_one("matchups")


def test_per_patch_304_reuses_per_patch_cache(isolated_cache):
    """A 304 for ``matchups_<patch>`` must read the per-patch cache body,
    not the (non-existent) plain ``matchups.json`` path."""
    patch_id = "16.1"
    cached = {"__meta": {"schema_version": 1}, "rows": [{"id": 7}]}
    (isolated_cache / f"matchups_{patch_id}.json").write_text(
        json.dumps(cached), encoding="utf-8"
    )
    (isolated_cache / f"matchups_{patch_id}.meta.json").write_text(
        json.dumps({"etag": 'W/"shard-old"'}),
        encoding="utf-8",
    )
    with patch(
        "lolalytics_api.json_repo.requests.get",
        return_value=_make_resp(304, headers={"ETag": 'W/"shard-old"'}),
    ) as get:
        rows = json_repo._fetch_one("matchups", patch_id)

    assert rows == [{"id": 7}]
    sent = get.call_args.kwargs["headers"]
    assert sent.get("If-None-Match") == 'W/"shard-old"'
    # Confirm the URL actually carried the patch suffix.
    called_url = get.call_args.args[0]
    assert called_url.endswith(f"/matchups_{patch_id}.json")
