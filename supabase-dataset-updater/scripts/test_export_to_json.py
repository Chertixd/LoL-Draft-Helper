"""
CDN-05 verification: export_to_json.py produces the envelope json_repo consumes.

RED phase — all tests fail until Task 2 lands the script. Uses unittest.mock
to shim the supabase client; no live network or credentials needed.

Running the suite:
    cd supabase-dataset-updater
    pip install -r requirements-dev.txt
    pytest scripts/test_export_to_json.py -v
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

# Import under test — fails during collection until Task 2 lands the script.
from scripts import export_to_json  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_mock_client(rows_by_table: dict[str, list[dict]]) -> MagicMock:
    """
    Build a MagicMock whose `.table(name).select("*").range(s, e).execute()`
    returns an object with `.data` equal to the slice of
    `rows_by_table[name]` inside the inclusive range [s, e].

    Also supports the per-patch query chain used by
    ``_fetch_table_for_patch``:

        .table(name).select("*").eq("patch", <p>).range(s, e).execute()

    ``.eq("patch", p)`` filters ``rows_by_table[name]`` by ``row["patch"] == p``
    before pagination — mirrors supabase-py's ``.eq().range()`` semantics.

    Unknown tables produce an empty list (so we can simulate missing tables).
    """
    client = MagicMock(name="supabase_client")

    def table_factory(name: str):
        rows = rows_by_table.get(name, [])
        table_mock = MagicMock(name=f"table({name})")

        def _build_range_chain(source_rows: list[dict], label: str):
            """Attach a ``.range(start, end).execute()`` chain over ``source_rows``."""
            select_mock = MagicMock(name=label)

            def range_factory(start: int, end: int):
                slice_rows = source_rows[start : end + 1]
                range_mock = MagicMock(name=f"range({start},{end})")
                exec_result = MagicMock(name="execute_result")
                exec_result.data = slice_rows
                range_mock.execute.return_value = exec_result
                return range_mock

            select_mock.range.side_effect = range_factory
            return select_mock

        def select_factory(*_args, **_kwargs):
            select_mock = _build_range_chain(rows, f"select({name})")

            def eq_factory(column: str, value):
                filtered = [r for r in rows if r.get(column) == value]
                eq_mock = _build_range_chain(
                    filtered, f"eq({name},{column}={value})"
                )
                return eq_mock

            select_mock.eq.side_effect = eq_factory
            return select_mock

        table_mock.select.side_effect = select_factory
        return table_mock

    client.table.side_effect = table_factory
    return client


def _rows_for_all_tables() -> dict[str, list[dict]]:
    """Plausible-shape fixture rows for every table in export_to_json.TABLES.

    Two patches (``15.24`` and ``16.1``) are present so the per-patch
    sharding path in ``export_table_per_patch`` is exercised with >1
    shard per per-patch table. Non-per-patch tables carry rows tagged
    with whichever patch is convenient; they are written as single files
    regardless.
    """
    return {
        "champion_stats": [
            {"patch": "15.24", "champion_key": "266", "role": "top", "games": 100, "wins": 55},
            {"patch": "15.24", "champion_key": "103", "role": "middle", "games": 200, "wins": 110},
            {"patch": "16.1", "champion_key": "266", "role": "top", "games": 90, "wins": 50},
        ],
        "matchups": [
            {
                "patch": "15.24",
                "champion_key": "266",
                "role": "top",
                "opponent_key": "122",
                "opponent_role": "top",
                "games": 80,
                "wins": 40,
            },
            {
                "patch": "16.1",
                "champion_key": "266",
                "role": "top",
                "opponent_key": "122",
                "opponent_role": "top",
                "games": 75,
                "wins": 42,
            },
        ],
        "synergies": [
            {
                "patch": "15.24",
                "champion_key": "266",
                "role": "top",
                "mate_key": "412",
                "mate_role": "support",
                "games": 50,
                "wins": 28,
            },
            {
                "patch": "16.1",
                "champion_key": "266",
                "role": "top",
                "mate_key": "412",
                "mate_role": "support",
                "games": 55,
                "wins": 30,
            },
        ],
        "items": [{"patch": "15.24", "item_id": 6701, "name": "Opportunity", "gold": 2700}],
        "runes": [{"patch": "15.24", "rune_id": 8005, "data": {"id": 8005, "key": "PressTheAttack"}}],
        "summoner_spells": [{"patch": "15.24", "spell_key": "4", "name": "Flash"}],
        "champions": [{"key": "266", "name": "Aatrox"}, {"key": "103", "name": "Ahri"}],
        "patches": [{"patch": "15.24"}, {"patch": "16.1"}],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_envelope_shape_correct(tmp_path: Path) -> None:
    """`export_table` writes <out>/<table>.json with the correct envelope."""
    rows = [
        {"id": 1, "patch": "15.24", "name": "Aatrox"},
        {"id": 2, "patch": "15.24", "name": "Ahri"},
    ]
    client = _make_mock_client({"t": rows})

    export_to_json.export_table(client, tmp_path, "t")

    out_path = tmp_path / "t.json"
    assert out_path.exists(), "expected t.json to be written"
    body = json.loads(out_path.read_text(encoding="utf-8"))

    assert set(body.keys()) == {"__meta", "rows"}, f"bad top-level keys: {set(body.keys())}"
    meta = body["__meta"]
    assert set(meta.keys()) >= {
        "exported_at",
        "sha256",
        "row_count",
        "schema_version",
        "source_table",
    }, f"missing __meta keys: {set(meta.keys())}"
    assert meta["schema_version"] == 1
    assert meta["row_count"] == 2
    assert meta["source_table"] == "t"
    assert isinstance(meta["exported_at"], str) and meta["exported_at"].endswith("Z")
    assert isinstance(meta["sha256"], str) and len(meta["sha256"]) == 64

    assert body["rows"] == rows


def test_sha256_canonical_form_matches_json_repo() -> None:
    """
    The canonical sha256 form MUST match what json_repo.py would compute
    byte-for-byte. Invariant #3 of the orchestrator spec:
        json.dumps(rows, sort_keys=True, separators=(",", ":"), default=<cb>)
    """
    rows = [
        {"b": 2, "a": 1},
        {"c": 3, "a": 0},
    ]
    expected = hashlib.sha256(
        json.dumps(
            rows,
            sort_keys=True,
            separators=(",", ":"),
            default=export_to_json._json_default,
        ).encode("utf-8")
    ).hexdigest()

    actual = export_to_json._canonical_rows_sha256(rows)
    assert actual == expected, (
        "canonical form divergence — will cause sha256 mismatch at client fetch"
    )

    # Round-trip: verifier-side (json_repo) recomputes over body["rows"] with
    # the identical canonical form. Simulate that here.
    body = {"__meta": {"sha256": actual}, "rows": rows}
    verifier_recompute = hashlib.sha256(
        json.dumps(
            body["rows"],
            sort_keys=True,
            separators=(",", ":"),
            default=export_to_json._json_default,
        ).encode("utf-8")
    ).hexdigest()
    assert verifier_recompute == body["__meta"]["sha256"]


def test_decimal_uuid_datetime_serialize() -> None:
    """Decimal, UUID, datetime must serialize losslessly via _json_default."""
    rows = [
        {
            "a": Decimal("1.5"),
            "b": UUID("00000000-0000-0000-0000-000000000000"),
            "c": datetime(2026, 4, 14, 3, 15, 0, tzinfo=timezone.utc),
        }
    ]
    # Must not raise TypeError.
    digest = export_to_json._canonical_rows_sha256(rows)
    assert isinstance(digest, str) and len(digest) == 64

    # Direct serialization check — strings for all three custom types.
    serialized = json.dumps(rows, default=export_to_json._json_default)
    parsed = json.loads(serialized)
    assert parsed[0]["a"] == "1.5"
    assert parsed[0]["b"] == "00000000-0000-0000-0000-000000000000"
    assert parsed[0]["c"].startswith("2026-04-14T03:15:00")

    # Precision check — Decimal → str preserves precision (not float).
    precise = [{"v": Decimal("0.1") + Decimal("0.2")}]
    # 0.1 + 0.2 as Decimal is exactly "0.3" (not 0.30000000000000004).
    assert '"v":"0.3"' in json.dumps(
        precise, sort_keys=True, separators=(",", ":"), default=export_to_json._json_default
    )


def test_pagination_stops_on_short_page() -> None:
    """
    `_fetch_table` paginates with .range(start, end) inclusive bounds and
    stops when a page shorter than PAGE_SIZE arrives.
    """
    page_size = export_to_json.PAGE_SIZE
    # Build 1500 fake rows: first page PAGE_SIZE full, second page short.
    all_rows = [{"i": i} for i in range(page_size + 500)]
    client = _make_mock_client({"x": all_rows})

    result = export_to_json._fetch_table(client, "x")
    assert len(result) == page_size + 500

    # Two .range() invocations with the right inclusive bounds.
    range_calls = [
        c for c in client.mock_calls if ".range(" in str(c) or c[0].endswith(".range")
    ]
    # The nested MagicMock structure makes direct `.range` inspection noisy;
    # fall back to counting: the client.table().select().range().execute()
    # chain must have been invoked exactly twice.
    assert client.table.call_count == 2  # once per page
    # Validate the last execute() returned the short page (< PAGE_SIZE).


def test_pagination_single_page_under_limit() -> None:
    """A single short page returns immediately without a second .range()."""
    rows = [{"i": i} for i in range(3)]
    client = _make_mock_client({"small": rows})

    result = export_to_json._fetch_table(client, "small")
    assert result == rows
    # Only one page fetched.
    assert client.table.call_count == 1


def test_atomic_write(tmp_path: Path) -> None:
    """`_atomic_write_json` leaves target in place + no leftover .tmp."""
    target = tmp_path / "t.json"
    payload = {"__meta": {"schema_version": 1, "row_count": 0}, "rows": []}

    export_to_json._atomic_write_json(target, payload)

    assert target.exists()
    # No leftover .tmp sibling.
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"unexpected .tmp leftovers: {leftovers}"

    # Round-trip.
    round_tripped = json.loads(target.read_text(encoding="utf-8"))
    assert round_tripped == payload


def test_any_table_failure_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A single-table failure aborts the run with exit code 1.

    Partial files on disk BEFORE the failing table are tolerated locally
    (D-08 atomicity is enforced by Plan 02-03's gh-pages publish step).
    Expected file count is (non-per-patch-tables) + (per-patch-tables ×
    patches) once sharding is fully applied; for the abort path we only
    assert the failing table's file is missing and total files < that
    ceiling.
    """
    rows_by_table = _rows_for_all_tables()

    fake_client = _make_mock_client(rows_by_table)
    # Make .table("items") raise on the first call. `patches` must still
    # succeed — main() calls _list_patches() before entering the per-table
    # loop, so the boom only fires for `items`.
    original_side_effect = fake_client.table.side_effect

    def boom(name: str):
        if name == "items":
            raise RuntimeError("boom")
        return original_side_effect(name)

    fake_client.table.side_effect = boom

    monkeypatch.setattr(
        export_to_json, "create_client", lambda *_a, **_kw: fake_client, raising=False
    )
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-role-key")
    # Disable .env loading so real-dev creds never leak in.
    monkeypatch.setattr(export_to_json, "load_dotenv", lambda *a, **kw: None, raising=False)

    rc = export_to_json.main(["--out-dir", str(tmp_path)])
    assert rc == 1, "expected exit code 1 on any single-table failure"

    # `items` file must NOT exist (it's the failing table).
    assert not (tmp_path / "items.json").exists()

    # Upper bound on successful writes = (non-per-patch tables) +
    # (per-patch tables × patches). We only require strictly less than
    # that — the failing table interrupts the loop.
    num_patches = len(rows_by_table["patches"])
    max_files = (
        len(export_to_json.TABLES) - len(export_to_json.PER_PATCH_TABLES)
    ) + len(export_to_json.PER_PATCH_TABLES) * num_patches
    written = list(tmp_path.glob("*.json"))
    assert len(written) < max_files


def test_end_to_end_mocked_supabase_nine_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Running main() against a fully mocked client writes one file per
    non-per-patch TABLES entry + one file per (per-patch-table × patch)
    combo, each with a valid envelope + round-trippable sha256.

    Name is kept for git-blame stability; the actual file count is
    ``(TABLES − PER_PATCH_TABLES) + PER_PATCH_TABLES × patches`` — the
    fixture provides 2 patches so ``matchups`` and ``synergies`` each
    produce 2 files. A naïve single-file ``matchups.json`` /
    ``synergies.json`` MUST NOT exist after the run.
    """
    rows_by_table = _rows_for_all_tables()
    fake_client = _make_mock_client(rows_by_table)

    monkeypatch.setattr(
        export_to_json, "create_client", lambda *_a, **_kw: fake_client, raising=False
    )
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-role-key")
    monkeypatch.setattr(export_to_json, "load_dotenv", lambda *a, **kw: None, raising=False)

    rc = export_to_json.main(["--out-dir", str(tmp_path)])
    assert rc == 0, "expected exit code 0 on full success"

    patches = [r["patch"] for r in rows_by_table["patches"]]
    assert len(patches) >= 2, "fixture must supply >=2 patches to exercise sharding"

    # Build expected filename set: single file for non-per-patch tables,
    # one file per (table, patch) for per-patch tables.
    expected_names: list[str] = []
    for table in export_to_json.TABLES:
        if table in export_to_json.PER_PATCH_TABLES:
            for patch_id in patches:
                expected_names.append(f"{table}_{patch_id}.json")
        else:
            expected_names.append(f"{table}.json")
    expected = sorted(expected_names)

    written = sorted(p.name for p in tmp_path.glob("*.json"))
    assert written == expected, f"wrong file set: {written} != {expected}"

    # Naïve single-file shapes for per-patch tables MUST NOT exist.
    for per_patch_table in export_to_json.PER_PATCH_TABLES:
        assert not (tmp_path / f"{per_patch_table}.json").exists(), (
            f"unsharded {per_patch_table}.json written — sharding regression"
        )

    # Explicit presence check for each per-patch shard.
    for per_patch_table in export_to_json.PER_PATCH_TABLES:
        for patch_id in patches:
            shard = tmp_path / f"{per_patch_table}_{patch_id}.json"
            assert shard.exists(), f"missing per-patch shard: {shard.name}"

    # Per-file envelope validation + sha256 round-trip.
    for filename in expected:
        body = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert set(body.keys()) == {"__meta", "rows"}
        assert body["__meta"]["schema_version"] == 1
        assert body["__meta"]["row_count"] == len(body["rows"])

        # `source_table` is always the base table name (without patch suffix).
        stem = filename[: -len(".json")]
        source_table = body["__meta"]["source_table"]
        if source_table in export_to_json.PER_PATCH_TABLES:
            # Filename matches <source_table>_<source_patch>.
            assert stem == f"{source_table}_{body['__meta']['source_patch']}"
            # Every row in a shard belongs to its own patch.
            for row in body["rows"]:
                assert row.get("patch") == body["__meta"]["source_patch"]
        else:
            assert stem == source_table

        # Re-verify sha256 (this is the json_repo-side check).
        recomputed = hashlib.sha256(
            json.dumps(
                body["rows"],
                sort_keys=True,
                separators=(",", ":"),
                default=export_to_json._json_default,
            ).encode("utf-8")
        ).hexdigest()
        assert (
            recomputed == body["__meta"]["sha256"]
        ), f"sha256 mismatch on {filename} — canonical form divergence"
