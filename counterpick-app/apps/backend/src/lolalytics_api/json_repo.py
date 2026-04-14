"""
CDN-backed read repository. Mirrors the public API of supabase_repo.py exactly.

CONTRACT: All 7 public ``get_*`` functions return values structurally
identical to the matching ``supabase_repo`` function. Contract-equivalence
is asserted by ``test_json_repo_contract.py`` (landed in Plan 02-04); do
NOT change return shapes here without updating both modules and the
contract test.

CRITICAL: This module MUST NOT import from ``lolalytics_api.supabase_repo``,
``lolalytics_api.supabase_client``, or ``lolalytics_api.config`` — any of
those pulls in the ``supabase`` package chain and defeats the Phase 2
supabase-removal goal (CONTEXT D-23, D-24; commit ``451e8f7`` is the
cautionary tale). Pure helpers (``_wilson_score``, ``_normalize_slug``,
``_attach_names``) are COPIED verbatim from ``supabase_repo.py`` per
orchestrator resolution #2 (Option b — copy, do not re-import).

Requirements: CDN-01 (API parity), CDN-02 (cache layout), CDN-03
(conditional GET), CDN-04 (corrupt-cache recovery).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# CONTEXT D-12 (orchestrator resolution #2): pure helpers copied verbatim
# below (NOT re-imported from supabase_repo) to keep the supabase chain
# out of this module's import graph. Sources: supabase_repo.py lines
# 6–22 (_wilson_score), 25–29 (_normalize_slug), 99–105 (_attach_names).
from lolalytics_api.resources import user_cache_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# CONTEXT D-20 + orchestrator resolution #3: baked-in default is the
# production GitHub Pages URL (verified from ``git remote -v``; lowercase
# user segment per GitHub Pages). Env override is for local testing only
# — the frozen .exe Tauri-spawned child cannot receive env vars from the
# user, so the default must be correct for production ship.
CDN_BASE_URL = os.environ.get(
    "CDN_BASE_URL",
    "https://chertixd.github.io/LoL-Draft-Helper/data",
)

# CONTEXT D-21: connect=5s, read=15s. Bounds the worst-case wait for one
# request; the largest table (matchups, ~800 KB) fits comfortably.
_HTTP_TIMEOUT = (5, 15)

# CONTEXT D-16 + orchestrator resolution #1: 9 workers because we fan out
# 9 tables concurrently (the 7 data tables + ``champions`` + ``patches``
# that resolve slug→key and latest patch respectively).
_FAN_OUT_MAX_WORKERS = 9

# CONTEXT D-04 + orchestrator resolution #1: full table list exported by
# Plan 02-02 and consumed here. Ordering is irrelevant to correctness.
_TABLES: Tuple[str, ...] = (
    "champion_stats",
    "champion_stats_by_role",
    "matchups",
    "synergies",
    "items",
    "runes",
    "summoner_spells",
    "champions",
    "patches",
)

# CONTEXT D-05: client supports schema_version ≤ 1. Exported envelopes
# with a higher version are rejected so a future v2 export cannot
# silently deliver unexpected fields to a v1 client.
_SCHEMA_VERSION_MAX = 1


class CDNError(RuntimeError):
    """Raised on unrecoverable CDN failure.

    Triggers: HTTP 4xx/5xx, unreachable CDN with no local cache,
    ``__meta.sha256`` mismatch against canonical ``rows`` serialization,
    ``__meta.schema_version`` above ``_SCHEMA_VERSION_MAX``.
    """


# ---------------------------------------------------------------------------
# Pure helpers — COPIED VERBATIM from supabase_repo.py (see CRITICAL note
# above). Do NOT ``from lolalytics_api.supabase_repo import ...`` — that
# triggers the supabase package chain.
# ---------------------------------------------------------------------------


def _wilson_score(wins: int, n: int, z: float = 1.44) -> float:
    """
    Berechnet die statistisch sichere untere Grenze der Winrate.
    Löst das "Low Sample Size"-Problem ohne harte Caps.

    Args:
        wins: Anzahl der Siege
        n: Anzahl der Spiele
        z: Z-Wert für Konfidenzintervall (1.44 = ~85% Sicherheit)
    """
    if n == 0:
        return 0.0
    phat = wins / n
    denominator = 1 + z**2 / n
    center_adjusted_probability = phat + z**2 / (2 * n)
    adjusted_standard_deviation = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)
    return (center_adjusted_probability - adjusted_standard_deviation) / denominator


def _normalize_slug(name: str) -> str:
    slug = name.lower()
    for ch in ["'", " ", "."]:
        slug = slug.replace(ch, "")
    return slug


def _attach_names(
    rows: List[Dict[str, Any]], key_to_name: Dict[str, str], key_field: str
) -> List[Dict[str, Any]]:
    for row in rows:
        target_key = row.get(key_field)
        row["name"] = key_to_name.get(target_key, target_key)
    return rows


# ---------------------------------------------------------------------------
# Cache primitives + conditional-GET fetch layer
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    """CONTEXT D-13: ``cdn/`` subdir under ``user_cache_dir()``.

    Created lazily on first use. Kept as a function (not a module-level
    constant) so unit tests can ``monkeypatch`` this symbol to redirect
    to a ``tmp_path``.
    """
    p = user_cache_dir() / "cdn"
    p.mkdir(parents=True, exist_ok=True)
    return p


# CONTEXT D-19: per-table staleness flag. True = last fetch used the
# local cache because the CDN was unreachable. Surfaced via
# ``stale_status()`` for ``/api/health`` in Phase 3.
_stale_state: Dict[str, bool] = {}
_stale_state_lock = threading.Lock()

# In-memory row cache populated by ``warm_cache()`` at startup (and
# lazily by ``_table()`` in dev mode). Read-heavy, write-rare — guarded
# by a Lock so the concurrent ``warm_cache`` populate is safe.
_data: Dict[str, List[Dict[str, Any]]] = {}
_data_lock = threading.Lock()


def _atomic_write_json(path: Path, payload: Any) -> None:
    """CONTEXT D-17: write ``path.tmp`` then ``os.replace`` onto ``path``.

    Atomic on Windows (NTFS ``MoveFileEx(..., MOVEFILE_REPLACE_EXISTING)``)
    and POSIX (``rename(2)``). Never leaves a half-written body for a
    reader to trip over.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def _load_meta(table: str) -> Optional[dict]:
    """Read ``<table>.meta.json`` or return ``None`` on missing/corrupt.

    CONTEXT D-18: corrupt meta → delete both meta + body, return None so
    the caller forces a fresh fetch.
    """
    meta_path = _cache_dir() / f"{table}.meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning(
            "[json_repo] corrupt meta for %s, deleting cache pair", table
        )
        meta_path.unlink(missing_ok=True)
        (_cache_dir() / f"{table}.json").unlink(missing_ok=True)
        return None


def _load_body(table: str) -> Optional[dict]:
    """Read ``<table>.json`` or return ``None`` on missing/corrupt.

    CONTEXT D-18: corrupt body → delete both meta + body.
    """
    body_path = _cache_dir() / f"{table}.json"
    if not body_path.exists():
        return None
    try:
        return json.loads(body_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning(
            "[json_repo] corrupt body for %s, deleting cache pair", table
        )
        body_path.unlink(missing_ok=True)
        (_cache_dir() / f"{table}.meta.json").unlink(missing_ok=True)
        return None


def _fetch_one(table: str) -> List[Dict[str, Any]]:
    """Conditional-GET one table; return its ``rows`` list.

    Happy path (200): verify schema_version + sha256, atomically write
    body + meta, clear stale flag, return rows.
    304: reuse cached body, clear stale flag.
    Network error + cache present: return cached rows, SET stale flag.
    Network error + no cache: raise CDNError.
    4xx/5xx, schema_version > 1, sha256 mismatch: raise CDNError.
    """
    url = f"{CDN_BASE_URL}/{table}.json"
    meta = _load_meta(table)
    headers: Dict[str, str] = {}
    if meta:
        etag = meta.get("etag")
        if etag:
            headers["If-None-Match"] = etag
        last_mod = meta.get("last_modified")
        if last_mod:
            headers["If-Modified-Since"] = last_mod

    try:
        resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        # CONTEXT D-19: unreachable CDN — fall back to cache + stale flag.
        body = _load_body(table)
        if body is not None:
            with _stale_state_lock:
                _stale_state[table] = True
            logger.warning(
                "[json_repo] CDN unreachable, using cached %s (stale)", table
            )
            return body.get("rows", [])
        # No cache on disk → loud failure. Phase 3 UX wraps this in a
        # friendly banner; for now backend startup aborts.
        raise CDNError(f"CDN unreachable and no cache for {table}: {exc}") from exc

    if resp.status_code == 304:
        body = _load_body(table)
        if body is None:
            # Degenerate: server said "not modified" but our cache
            # vanished. Drop the ETag and force a full refetch.
            logger.warning(
                "[json_repo] 304 but cache missing for %s; refetching", table
            )
            return _fetch_one_unconditional(table)
        with _stale_state_lock:
            _stale_state[table] = False
        return body.get("rows", [])

    if resp.status_code != 200:
        snippet = (resp.text or "")[:200]
        raise CDNError(
            f"CDN returned {resp.status_code} for {table}: {snippet}"
        )

    body = resp.json()  # shape: {"__meta": {...}, "rows": [...]}

    # CONTEXT D-05: schema_version enforcement (forward-compat guard).
    meta_block = body.get("__meta") or {}
    schema_v = meta_block.get("schema_version")
    if schema_v is None or schema_v > _SCHEMA_VERSION_MAX:
        raise CDNError(
            f"Unsupported schema_version={schema_v} for {table}; "
            f"client supports {_SCHEMA_VERSION_MAX}"
        )
    if schema_v < _SCHEMA_VERSION_MAX:
        logger.warning(
            "[json_repo] %s has older schema_version=%d; proceeding",
            table,
            schema_v,
        )

    # CONTEXT D-05: verify __meta.sha256 against canonical(rows).
    # CRITICAL: the exact serialization form (``sort_keys=True,
    # separators=(",", ":")``) is the orchestrator cross-side hash
    # invariant — Plan 02-02's exporter uses the identical form.
    rows = body.get("rows", [])
    expected = meta_block.get("sha256")
    actual = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if expected and expected != actual:
        raise CDNError(
            f"sha256 mismatch for {table}: expected {expected}, got {actual}"
        )

    # CONTEXT D-17: atomic write body + sibling meta.
    cache = _cache_dir()
    _atomic_write_json(cache / f"{table}.json", body)
    _atomic_write_json(
        cache / f"{table}.meta.json",
        {
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "fetched_at": resp.headers.get("Date"),
            "sha256": expected,
        },
    )
    with _stale_state_lock:
        _stale_state[table] = False
    logger.info("[json_repo] fetched %s (%d rows)", table, len(rows))
    return rows


def _fetch_one_unconditional(table: str) -> List[Dict[str, Any]]:
    """Drop the cache pair and force a 200. Recovery helper for 304+missing."""
    cache = _cache_dir()
    (cache / f"{table}.json").unlink(missing_ok=True)
    (cache / f"{table}.meta.json").unlink(missing_ok=True)
    return _fetch_one(table)


def warm_cache() -> None:
    """Startup fan-out: 9 conditional GETs in parallel, populate ``_data``.

    Called from ``backend.py main()`` in Plan 02-04. Any ``CDNError`` from
    a worker future propagates and aborts startup (loud-fail per D-19).
    """
    with ThreadPoolExecutor(max_workers=_FAN_OUT_MAX_WORKERS) as ex:
        future_to_table = {ex.submit(_fetch_one, t): t for t in _TABLES}
        results: Dict[str, List[Dict[str, Any]]] = {}
        for fut in as_completed(future_to_table):
            t = future_to_table[fut]
            results[t] = fut.result()  # propagates CDNError on failure
    with _data_lock:
        _data.update(results)
    logger.info("[json_repo] warm_cache complete; %d tables loaded", len(results))


def stale_status() -> Dict[str, bool]:
    """Snapshot of per-table stale flags for ``/api/health`` (Phase 3)."""
    with _stale_state_lock:
        return dict(_stale_state)


def _table(name: str) -> List[Dict[str, Any]]:
    """Return the row list for ``name``; lazy-fetch on cache miss.

    Usually populated by ``warm_cache()`` at startup. Dev mode / cold
    call without warm-up → single synchronous fetch.
    """
    with _data_lock:
        if name in _data:
            return _data[name]
    rows = _fetch_one(name)
    with _data_lock:
        _data[name] = rows
    return rows


# ---------------------------------------------------------------------------
# Data-access helpers — reimplemented against the cache (CONTEXT D-12).
# These mirror supabase_repo's helpers but read from ``_table(...)``
# instead of ``supabase.table(...).select(...).execute()``.
# ---------------------------------------------------------------------------


def _champion_map() -> Dict[str, Any]:
    """Return ``{"slug_map": {slug: (key, name)}, "key_to_name": {key: name}}``.

    Reads the exported ``champions`` table (orchestrator resolution #1).
    Each row has shape ``{"key": str, "name": str}`` — same schema as
    ``supabase_repo._champion_map`` returns from Supabase.
    """
    slug_map: Dict[str, Tuple[str, str]] = {}
    key_to_name: Dict[str, str] = {}
    for row in _table("champions"):
        key = row["key"]
        name = row["name"]
        slug = _normalize_slug(name)
        slug_map[slug] = (key, name)
        key_to_name[key] = name
    return {"slug_map": slug_map, "key_to_name": key_to_name}


def _get_latest_patch(fallback: Optional[str] = None) -> str:
    """Return the most recent exported patch.

    Reads the exported ``patches`` table (orchestrator resolution #1).
    supabase_repo sorts by ``created_at desc limit 1``; we do the same
    if ``created_at`` is present, else fall back to ``max(patch)``.
    """
    rows = _table("patches")
    if rows:
        # Prefer ``created_at`` ordering to match supabase_repo behavior
        # exactly. Fall back to ``patch`` string ordering if absent.
        try:
            rows_sorted = sorted(
                rows,
                key=lambda r: (r.get("created_at") or "", r.get("patch") or ""),
                reverse=True,
            )
            return rows_sorted[0]["patch"]
        except (KeyError, TypeError):
            return max(r["patch"] for r in rows)
    if fallback:
        return fallback
    raise RuntimeError("No patch found in CDN data.")


def _resolve_champion(champion: str) -> Tuple[str, str]:
    """Slug-tolerant lookup; matches supabase_repo._resolve_champion exactly."""
    maps = _champion_map()
    slug_map = maps["slug_map"]
    key_to_name = maps["key_to_name"]
    slug = _normalize_slug(champion)
    if slug in slug_map:
        key, name = slug_map[slug]
        return key, name
    # Fallback: caller passed a champion key directly.
    if champion in key_to_name:
        return champion, key_to_name[champion]
    raise ValueError(f"Champion '{champion}' not found in CDN data.")


def _determine_role(
    champion_key: str, patch: str, requested_role: Optional[str]
) -> str:
    """Pick the requested role, else the most-played role for this patch."""
    if requested_role:
        return requested_role
    rows = [
        r
        for r in _table("champion_stats")
        if r.get("patch") == patch and r.get("champion_key") == champion_key
    ]
    if not rows:
        raise ValueError(
            f"No stats found for champion {champion_key} and patch {patch}."
        )
    rows.sort(key=lambda r: r.get("games", 0) or 0, reverse=True)
    return rows[0]["role"]


# ---------------------------------------------------------------------------
# Public API — mirrors supabase_repo.py exactly (CONTEXT D-11).
# Build method: copy-modify each supabase_repo function, replacing every
# ``supabase.table("X").select(...).eq(...).execute().data`` with a
# list-comprehension filter over ``_table("X")``. All post-processing
# (wilson, delta, normalized_delta, sort, slice, attach_names) is
# preserved verbatim — including German comments per project convention.
# ---------------------------------------------------------------------------


def get_champion_stats(
    champion: str, role: Optional[str] = None, patch: Optional[str] = None
) -> Dict[str, Any]:
    patch = patch or _get_latest_patch()
    champion_key, champion_name = _resolve_champion(champion)
    role = _determine_role(champion_key, patch, role)

    rows = [
        r
        for r in _table("champion_stats")
        if r.get("patch") == patch
        and r.get("champion_key") == champion_key
        and r.get("role") == role
    ][:1]
    if not rows:
        raise RuntimeError(
            f"No champion_stats row for champion={champion}, role={role}, patch={patch}"
        )
    row = rows[0]
    games = row.get("games", 0) or 0
    wins = row.get("wins", 0) or 0
    winrate = wins / games if games > 0 else 0
    return {
        "champion": champion_name,
        "champion_key": champion_key,
        "role": role,
        "patch": patch,
        "games": games,
        "wins": wins,
        "winrate": winrate,
        "damage_profile": row.get("damage_profile"),
        "stats_by_time": row.get("stats_by_time"),
    }


def get_matchups(
    champion: str,
    role: Optional[str] = None,
    opponent_role: Optional[str] = None,
    patch: Optional[str] = None,
    limit: int = 10,
    ascending: bool = True,
    min_games_pct: float = 0.003,  # 0.3% der Champion-Gesamtspiele
) -> Dict[str, Any]:
    """
    Holt Matchup-Daten mit Delta-Berechnung relativ zur Base-WR.

    Returns:
        {
            "by_delta": [...],
            "by_normalized": [...],
            "base_winrate": float,
            "base_wilson": float,
            "role": str
        }
    """
    patch = patch or _get_latest_patch()
    champion_key, _ = _resolve_champion(champion)
    role = _determine_role(champion_key, patch, role)
    # Default: opponent_role = eigene Rolle (Support vs Support, etc.)
    opponent_role = opponent_role or role

    # Hole Gesamtstatistiken des Champions für diese Rolle (games UND wins)
    stats_rows = [
        r
        for r in _table("champion_stats")
        if r.get("patch") == patch
        and r.get("champion_key") == champion_key
        and r.get("role") == role
    ][:1]
    base_games = stats_rows[0]["games"] if stats_rows else 0
    base_wins = stats_rows[0]["wins"] if stats_rows else 0
    base_winrate = base_wins / base_games if base_games > 0 else 0.5
    base_wilson = _wilson_score(base_wins, base_games, z=1.44)

    # Hole alle Champion-Stats für die Gegner-Rolle (für Gegner-Base-WR)
    opponent_stats_rows = [
        r
        for r in _table("champion_stats")
        if r.get("patch") == patch and r.get("role") == opponent_role
    ]
    opponent_stats_map = {
        r["champion_key"]: {"games": r.get("games") or 0, "wins": r.get("wins") or 0}
        for r in opponent_stats_rows
    }
    total_role_games = sum(s["games"] for s in opponent_stats_map.values())

    rows = [
        r
        for r in _table("matchups")
        if r.get("patch") == patch
        and r.get("champion_key") == champion_key
        and r.get("role") == role
        and r.get("opponent_role") == opponent_role
    ]

    # Filter nach prozentualem Minimum an Matchup-Games (relativ zu
    # Champion-Gesamtspielen)
    min_games = int(base_games * min_games_pct)
    rows = [r for r in rows if (r.get("games", 0) or 0) >= min_games]

    # Compute winrate, Wilson Score, Delta zur Base-WR und Normalized Delta
    for row in rows:
        games = row.get("games", 0) or 0
        wins = row.get("wins", 0) or 0
        row["winrate"] = wins / games if games > 0 else 0
        row["wilson_score"] = _wilson_score(wins, games, z=1.28)
        row["delta"] = row["wilson_score"] - base_wilson

        # Gegner Base-WR und Normalized Delta berechnen
        opp_stats = opponent_stats_map.get(row["opponent_key"], {})
        opp_games = opp_stats.get("games", 0)
        opp_wins = opp_stats.get("wins", 0)
        row["opponent_base_wr"] = (
            opp_wins / opp_games if opp_games > 0 else 0.5
        )

        # normalized_delta nur bei gültigen Gegner-Stats berechnen
        if opp_games > 0:
            opp_wilson = _wilson_score(opp_wins, opp_games, z=1.44)
            # Erwartete WR gegen diesen Gegner = 1 - Gegner Base WR
            expected_wilson = 1 - opp_wilson
            row["normalized_delta"] = row["wilson_score"] - expected_wilson
        else:
            row["normalized_delta"] = None  # Keine gültigen Gegner-Stats

        # Füge Opponent Pickrate hinzu für Debug/Anzeige
        row["opponent_pickrate"] = (
            opp_games / total_role_games if total_role_games > 0 else 0
        )

    # Attach opponent names
    key_to_name = _champion_map()["key_to_name"]
    rows = _attach_names(rows, key_to_name, "opponent_key")

    # Erstelle zwei sortierte Listen: nach Delta und nach Normalized Delta
    # Counter mich = negative Deltas, Ich countere = positive Deltas
    if ascending:
        # Counter mich: negative Deltas, sortiert aufsteigend (schlechteste
        # zuerst)
        rows_by_delta = sorted(
            [r for r in rows if r["delta"] < 0], key=lambda r: r["delta"]
        )
        rows_by_normalized = sorted(
            [
                r
                for r in rows
                if r["normalized_delta"] is not None and r["normalized_delta"] < 0
            ],
            key=lambda r: r["normalized_delta"],
        )
    else:
        # Ich countere: positive Deltas, sortiert absteigend (beste zuerst)
        rows_by_delta = sorted(
            [r for r in rows if r["delta"] > 0],
            key=lambda r: r["delta"],
            reverse=True,
        )
        rows_by_normalized = sorted(
            [
                r
                for r in rows
                if r["normalized_delta"] is not None and r["normalized_delta"] > 0
            ],
            key=lambda r: r["normalized_delta"],
            reverse=True,
        )

    return {
        "by_delta": rows_by_delta[:limit],
        "by_normalized": rows_by_normalized[:limit],
        "base_winrate": base_winrate,
        "base_wilson": base_wilson,
        "role": role,
    }


def get_synergies(
    champion: str,
    role: Optional[str] = None,
    mate_role: Optional[str] = None,
    patch: Optional[str] = None,
    limit: int = 10,
    min_games_pct: float = 0.003,  # 0.3% der Gesamtspiele
) -> Dict[str, Any]:
    """
    Holt Synergie-Daten mit Delta-Berechnung relativ zur Base-WR.

    Returns:
        {
            "rows": [...],
            "base_winrate": float,
            "base_wilson": float,
            "role": str
        }
    """
    patch = patch or _get_latest_patch()
    champion_key, _ = _resolve_champion(champion)
    role = _determine_role(champion_key, patch, role)

    # Hole Gesamtstatistiken des Champions für diese Rolle (games UND wins)
    stats_rows = [
        r
        for r in _table("champion_stats")
        if r.get("patch") == patch
        and r.get("champion_key") == champion_key
        and r.get("role") == role
    ][:1]
    base_games = stats_rows[0]["games"] if stats_rows else 0
    base_wins = stats_rows[0]["wins"] if stats_rows else 0
    base_winrate = base_wins / base_games if base_games > 0 else 0.5
    base_wilson = _wilson_score(base_wins, base_games, z=1.44)

    min_games = int(base_games * min_games_pct)

    rows = [
        r
        for r in _table("synergies")
        if r.get("patch") == patch
        and r.get("champion_key") == champion_key
        and r.get("role") == role
    ]
    # Filter nach mate_role wenn angegeben
    if mate_role:
        rows = [r for r in rows if r.get("mate_role") == mate_role]

    # Filter nach prozentualer Mindestanzahl an Spielen
    rows = [r for r in rows if (r.get("games", 0) or 0) >= min_games]

    # Compute winrate, Wilson Score und Delta zur Base-WR
    for row in rows:
        games = row.get("games", 0) or 0
        wins = row.get("wins", 0) or 0
        row["winrate"] = wins / games if games > 0 else 0
        row["wilson_score"] = _wilson_score(wins, games, z=1.28)
        row["delta"] = row["wilson_score"] - base_wilson

    # Filter nach positivem Delta (nur gute Synergien anzeigen)
    rows = [r for r in rows if r["delta"] > 0]

    # Sortiere nach Delta absteigend (beste Synergien zuerst)
    rows.sort(key=lambda r: r["delta"], reverse=True)

    key_to_name = _champion_map()["key_to_name"]
    rows = _attach_names(rows, key_to_name, "mate_key")

    return {
        "rows": rows[:limit],
        "base_winrate": base_winrate,
        "base_wilson": base_wilson,
        "role": role,
    }


def get_items(patch: Optional[str] = None) -> List[Dict[str, Any]]:
    patch = patch or _get_latest_patch()
    return [r for r in _table("items") if r.get("patch") == patch]


def get_runes(patch: Optional[str] = None) -> List[Dict[str, Any]]:
    patch = patch or _get_latest_patch()
    return [r for r in _table("runes") if r.get("patch") == patch]


def get_summoner_spells(patch: Optional[str] = None) -> List[Dict[str, Any]]:
    patch = patch or _get_latest_patch()
    return [r for r in _table("summoner_spells") if r.get("patch") == patch]


def get_champion_stats_by_role(
    champion: str, patch: Optional[str] = None
) -> Dict[str, Any]:
    """
    Holt alle Rollen-Statistiken für einen Champion (für Role Predictor)
    Returns: {
        "champion_key": str,
        "champion_name": str,
        "statsByRole": {
            "0": {"games": int, "wins": int},  # top
            "1": {"games": int, "wins": int},  # jungle
            "2": {"games": int, "wins": int},  # middle
            "3": {"games": int, "wins": int},  # bottom
            "4": {"games": int, "wins": int}   # support
        }
    }
    """
    patch = patch or _get_latest_patch()
    champion_key, champion_name = _resolve_champion(champion)

    # Hole alle Rollen-Stats für diesen Champion
    rows = [
        r
        for r in _table("champion_stats")
        if r.get("patch") == patch and r.get("champion_key") == champion_key
    ]

    # Konvertiere zu statsByRole Format
    stats_by_role = {
        "0": {"games": 0, "wins": 0},  # top
        "1": {"games": 0, "wins": 0},  # jungle
        "2": {"games": 0, "wins": 0},  # middle
        "3": {"games": 0, "wins": 0},  # bottom
        "4": {"games": 0, "wins": 0},  # support
    }

    role_mapping = {
        "top": "0",
        "jungle": "1",
        "middle": "2",
        "bottom": "3",
        "support": "4",
    }

    for row in rows:
        role_name = (row.get("role") or "").lower()
        role_num = role_mapping.get(role_name)
        if role_num is not None:
            stats_by_role[role_num] = {
                "games": row.get("games", 0) or 0,
                "wins": row.get("wins", 0) or 0,
            }

    return {
        "champion_key": champion_key,
        "champion_name": champion_name,
        "statsByRole": stats_by_role,
    }
