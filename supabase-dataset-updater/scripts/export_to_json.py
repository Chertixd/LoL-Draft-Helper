"""
Daily Supabase → JSON exporter.

Reads service-role key from env. Writes `<out_dir>/<table>.json` files with
a __meta envelope per CONTEXT D-05 (exported_at, sha256, row_count,
schema_version, source_table). Designed to run inside
.github/workflows/update-dataset.yml after the existing TS ETL step (Plan
02-03 wires the workflow). CONTEXT D-08: a single table failure aborts the
entire run with exit code 1 — partial publishing is forbidden; the CI
pipeline's atomicity comes from peaceiris/actions-gh-pages@v4 publishing
the whole directory or not at all.

Canonical sha256 form (IDENTICAL to json_repo.py Plan 02-01 — orchestrator
critical invariant #3). Any divergence makes every client fetch fail with
"sha256 mismatch":

    json.dumps(rows, sort_keys=True, separators=(",", ":"),
               default=_json_default).encode("utf-8")

Requirements: CDN-05.

champion_stats.name verification (orchestrator resolution #4): NOT performed
— no .env / live Supabase creds available in the worktree at implementation
time. Defaulting to the conservative 9-table path (includes the dedicated
`champions` table for name lookups). If a future run of the verification
confirms `name` is already on `champion_stats` rows, `champions` can be
dropped from TABLES and json_repo._champion_map simplified.

Service-role key security (D-06, T-02-14): the key is read from env only,
never printed. Error messages to stderr contain only the table name and the
exception repr — callers must audit `exc` strings before adding them to CI
logs if the repr could include the Supabase URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from dotenv import load_dotenv
from supabase import Client, create_client

SCHEMA_VERSION = 1  # CONTEXT D-05
PAGE_SIZE = 1000  # supabase-py default page max; .range() uses inclusive bounds.

# Tables to export. Verified against live Supabase on 2026-04-15.
# `champion_stats_by_role` is NOT a table — it is a derived query over
# `champion_stats` (see supabase_repo.get_champion_stats_by_role). The client
# rebuilds it from champion_stats rows. `champions` and `patches` ship because
# `champion_stats` carries `champion_key` not `name`, so key→name resolution
# needs the `champions` table client-side.
TABLES: tuple[str, ...] = (
    "champion_stats",
    "matchups",
    "synergies",
    "items",
    "runes",
    "summoner_spells",
    "champions",
    "patches",
)

# Tables that must be sharded per-patch so individual files fit under the
# GitHub push limit (100 MB hard, ~50 MB soft). Verified against 2026-04-14
# production sizes: matchups.json = 224 MB, synergies.json = 170 MB in a
# single file; with 5 patches each shard is ~40 MB / ~34 MB, comfortably
# under both limits.
#
# The client (json_repo.py) mirrors this exact set; any change here REQUIRES
# a matching change in json_repo.PER_PATCH_TABLES — otherwise the client
# fetches a non-existent URL.
PER_PATCH_TABLES: frozenset[str] = frozenset({"matchups", "synergies"})


def _json_default(obj: Any) -> Any:
    """
    JSON-serialize the PostgreSQL types supabase-py may return.

    - Decimal → str (LOSSLESS; float would lose precision — Pitfall #1).
    - UUID → str.
    - datetime → ISO-8601 string via `isoformat()`.

    Any other type raises `TypeError` with a diagnostic message so missing
    type handling is surfaced loud (not silently swallowed).
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(
        f"Type {type(obj).__name__} not JSON-serializable: {obj!r}"
    )


def _canonical_rows_sha256(rows: list[dict]) -> str:
    """
    sha256 over the canonical JSON of `rows` only (no __meta), per D-05.

    Canonical form MUST be identical to json_repo._fetch_one's verification
    path (orchestrator critical invariant #3): same kwargs, same default=.
    """
    canonical = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _fetch_table(client: Client, table: str) -> list[dict]:
    """
    Paginate a Supabase table via .range(start, end) with inclusive bounds.

    End-of-table is signaled by a page shorter than PAGE_SIZE (the Supabase
    pagination primitive — see research Pattern 3). Rows accumulate into a
    single list returned to the caller.
    """
    all_rows: list[dict] = []
    start = 0
    while True:
        end = start + PAGE_SIZE - 1  # inclusive on both ends
        resp = client.table(table).select("*").range(start, end).execute()
        page = resp.data or []
        all_rows.extend(page)
        if len(page) < PAGE_SIZE:
            break  # short page → end of table
        start += PAGE_SIZE
    return all_rows


def _fetch_table_for_patch(
    client: Client, table: str, patch: str
) -> list[dict]:
    """
    Paginate a Supabase table filtered to a single patch.

    Same semantics as ``_fetch_table`` but with ``.eq("patch", patch)``
    in the query chain. Used by ``export_table_per_patch`` to produce
    one file per (table, patch) pair so individual files stay under
    GitHub's 100 MB push limit.
    """
    all_rows: list[dict] = []
    start = 0
    while True:
        end = start + PAGE_SIZE - 1  # inclusive on both ends
        resp = (
            client.table(table)
            .select("*")
            .eq("patch", patch)
            .range(start, end)
            .execute()
        )
        page = resp.data or []
        all_rows.extend(page)
        if len(page) < PAGE_SIZE:
            break  # short page → end of table
        start += PAGE_SIZE
    return all_rows


def _list_patches(client: Client) -> list[str]:
    """
    Return the list of distinct patch identifiers present in the ``patches``
    table. Order is preserved (Supabase returns insertion order by default);
    downstream consumers don't depend on sort order — each per-patch file
    carries its own __meta envelope.
    """
    rows = _fetch_table(client, "patches")
    # Deduplicate defensively even though the `patches` table is expected to
    # be unique — defense-in-depth against upstream schema drift.
    seen: set[str] = set()
    patches: list[str] = []
    for row in rows:
        p = row.get("patch")
        if p is None or p in seen:
            continue
        seen.add(p)
        patches.append(p)
    return patches


def _atomic_write_json(path: Path, payload: dict) -> None:
    """
    Atomic write via tmp-file + os.replace (Pattern 2).

    Same-volume rename is atomic on Windows NTFS and POSIX since Python 3.3.
    The final payload is serialized with the same `default=_json_default`
    callable as `_canonical_rows_sha256` so the on-disk file and the sha256
    envelope stay consistent.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, default=_json_default, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def export_table(client: Client, out_dir: Path, table: str) -> None:
    """
    Fetch one table → build the __meta envelope → atomic-write to <out>/<table>.json.
    """
    rows = _fetch_table(client, table)
    payload = {
        "__meta": {
            "exported_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "sha256": _canonical_rows_sha256(rows),
            "row_count": len(rows),
            "schema_version": SCHEMA_VERSION,
            "source_table": table,
        },
        "rows": rows,
    }
    out_path = out_dir / f"{table}.json"
    _atomic_write_json(out_path, payload)
    print(f"[export] {table}: {len(rows)} rows -> {out_path}")


def export_table_per_patch(
    client: Client, out_dir: Path, table: str, patches: list[str]
) -> None:
    """
    Shard one table into per-patch files: ``<table>_<patch>.json``.

    Each file carries its own ``__meta`` envelope with sha256 computed over
    that patch's row subset only — the canonical form is identical to
    ``export_table`` so the client-side verification in ``json_repo._fetch_one``
    is byte-compatible. Fails fast on the first (table, patch) error so the
    whole run aborts with a partial state that CI's publish step will discard.
    """
    for patch in patches:
        rows = _fetch_table_for_patch(client, table, patch)
        payload = {
            "__meta": {
                "exported_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "sha256": _canonical_rows_sha256(rows),
                "row_count": len(rows),
                "schema_version": SCHEMA_VERSION,
                "source_table": table,
                # `source_patch` pins the shard to its patch for any future
                # client-side sanity check; harmless to older clients.
                "source_patch": patch,
            },
            "rows": rows,
        }
        out_path = out_dir / f"{table}_{patch}.json"
        _atomic_write_json(out_path, payload)
        print(f"[export] {table}_{patch}: {len(rows)} rows -> {out_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """
    Entry point.

    argv is accepted for testability — production uses `sys.exit(main())`
    with the default None (argparse reads sys.argv[1:]). Returns 0 on full
    success, 1 on any single-table failure (D-08 atomic-or-nothing intent;
    filesystem atomicity is Plan 02-03's gh-pages publish step).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Export Supabase tables to JSON files with a __meta envelope "
            "(CDN-05). Designed to run inside the daily ETL workflow; also "
            "accepts --out-dir for local-dev runs."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("./public/data"),
        help="Directory to write <table>.json files into. Created if absent.",
    )
    args = parser.parse_args(argv)

    load_dotenv()  # local-dev only; CI sets env vars directly.

    try:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # D-06: service-role key
    except KeyError as exc:
        # Friendly error — do NOT print the value.
        print(
            f"[export] FATAL: missing required env var: {exc.args[0]}",
            file=sys.stderr,
        )
        return 1

    client = create_client(url, key)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve patch list eagerly so a per-patch table's first call doesn't
    # silently export zero shards. If the `patches` table is empty we let
    # the per-patch path raise — atomic-or-nothing (D-08) applies.
    try:
        patches = _list_patches(client)
    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        msg = str(exc)
        if url in msg:
            msg = msg.replace(url, "<redacted>")
        print(
            f"[export] FATAL: could not list patches: {msg}",
            file=sys.stderr,
        )
        return 1

    # CONTEXT D-08: atomic-or-nothing — fail fast on the first table error.
    for table in TABLES:
        try:
            if table in PER_PATCH_TABLES:
                if not patches:
                    # A per-patch table with zero patches is a degenerate
                    # state — the CDN would have no shards at all and the
                    # client would 404 on first read. Fail loud.
                    raise RuntimeError(
                        f"no patches found; cannot shard per-patch table {table!r}"
                    )
                export_table_per_patch(client, args.out_dir, table, patches)
            else:
                export_table(client, args.out_dir, table)
        except Exception as exc:  # noqa: BLE001 — intentional broad catch
            # T-02-11: redact `exc` if it happens to contain the URL.
            # supabase-py exceptions can include the project URL; replace
            # any occurrence with "<redacted>" before logging.
            msg = str(exc)
            if url in msg:
                msg = msg.replace(url, "<redacted>")
            print(f"[export] FATAL: {table} failed: {msg}", file=sys.stderr)
            return 1

    print(
        f"[export] all {len(TABLES)} tables exported to {args.out_dir} "
        f"(per-patch shards for: {sorted(PER_PATCH_TABLES)}; "
        f"{len(patches)} patches)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
