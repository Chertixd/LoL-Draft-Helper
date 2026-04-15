"""
CDN-01 verification: json_repo and supabase_repo return identical data.

Plan 02-04 (D-29): live-credential parity tests. One test per public function;
each runs BOTH supabase_repo.get_X(...) AND json_repo.get_X(...) with the same
args and asserts deep-equal on the result (modulo ordering for list-of-dicts).

Pitfall #7 mitigation: these tests require live Supabase + live CDN creds and
the explicit CDN_CONTRACT_TEST_ENABLE=1 opt-in. When either is missing the
entire module is skipped cleanly so PR CI (which lacks the creds) never
attempts them. CI scope: the daily ETL workflow runs `pytest -m contract`
with both gates set, after the export step lands fresh data.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import pytest

from lolalytics_api import json_repo, supabase_repo

# Pitfall #7 mitigation: skip when creds OR opt-in env var are absent.
# The double skip ensures the tests never surprise-run in local dev or on
# fork-PR CI — only in the daily cron that explicitly sets both.
pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(
        not (
            os.environ.get("SUPABASE_URL")
            and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        ),
        reason="contract test needs live Supabase credentials",
    ),
    pytest.mark.skipif(
        not os.environ.get("CDN_CONTRACT_TEST_ENABLE"),
        reason="contract test opt-in; set CDN_CONTRACT_TEST_ENABLE=1",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stable_sort(rows: List[Dict[str, Any]], keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    """Sort list-of-dicts by composite key so order-insensitive compare works.

    ``None`` values sort before any other value via the ``(v is None, v)``
    trick so rows with missing keys don't raise a TypeError on mixed types.
    """
    def _sort_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
        out: List[Any] = []
        for k in keys:
            v = row.get(k)
            out.append((v is None, v))
        return tuple(out)

    return sorted(rows, key=_sort_key)


def _assert_rows_equal(
    a: List[Dict[str, Any]], b: List[Dict[str, Any]], keys: Tuple[str, ...]
) -> None:
    """Deep-equal two list-of-dicts modulo ordering, on the given key tuple."""
    sa, sb = _stable_sort(a, keys), _stable_sort(b, keys)
    assert sa == sb, (
        f"row count: supabase={len(sa)} cdn={len(sb)}; "
        f"first diff: supabase={sa[0] if sa else None} cdn={sb[0] if sb else None}"
    )


def _discover_keys(sample_row: Dict[str, Any], preferred: Tuple[str, ...]) -> Tuple[str, ...]:
    """Return the first preferred tuple whose keys all exist in ``sample_row``;
    fall back to a deterministic 3-key projection of the row's own keys.

    Research assumption A3 — the stable-sort primary key for each table is
    not authoritatively documented; use the preferred tuple if available,
    else ``sorted(sample_row.keys())[:3]``.
    """
    if all(k in sample_row for k in preferred):
        return preferred
    return tuple(sorted(sample_row.keys()))[:3]


# ---------------------------------------------------------------------------
# One test per public function
# ---------------------------------------------------------------------------


def test_get_items_parity() -> None:
    a = supabase_repo.get_items()
    b = json_repo.get_items()
    assert a and b, "both sides must return non-empty rows for a meaningful compare"
    keys = _discover_keys(a[0], preferred=("patch", "item_id"))
    _assert_rows_equal(a, b, keys=keys)


def test_get_runes_parity() -> None:
    a = supabase_repo.get_runes()
    b = json_repo.get_runes()
    assert a and b, "both sides must return non-empty rows for a meaningful compare"
    keys = _discover_keys(a[0], preferred=("patch", "rune_id"))
    _assert_rows_equal(a, b, keys=keys)


def test_get_summoner_spells_parity() -> None:
    a = supabase_repo.get_summoner_spells()
    b = json_repo.get_summoner_spells()
    assert a and b, "both sides must return non-empty rows for a meaningful compare"
    keys = _discover_keys(a[0], preferred=("patch", "spell_key"))
    _assert_rows_equal(a, b, keys=keys)


def test_get_champion_stats_parity() -> None:
    # get_champion_stats returns a single dict (not a list) — structural equality.
    a = supabase_repo.get_champion_stats("Aatrox")
    b = json_repo.get_champion_stats("Aatrox")
    assert a == b


def test_get_champion_stats_by_role_parity() -> None:
    # Returns a dict with a nested ``statsByRole`` sub-dict — structural equality.
    a = supabase_repo.get_champion_stats_by_role("Ahri")
    b = json_repo.get_champion_stats_by_role("Ahri")
    assert a == b


def test_get_matchups_parity() -> None:
    a = supabase_repo.get_matchups("Lux", role="middle")
    b = json_repo.get_matchups("Lux", role="middle")
    # Top-level scalars: compare exactly (strings) or with approx (floats).
    assert a["role"] == b["role"]
    assert a["base_winrate"] == pytest.approx(b["base_winrate"])
    assert a["base_wilson"] == pytest.approx(b["base_wilson"])
    # Row lists: sort by opponent_key and deep-equal.
    _assert_rows_equal(a["by_delta"], b["by_delta"], keys=("opponent_key",))
    _assert_rows_equal(a["by_normalized"], b["by_normalized"], keys=("opponent_key",))


def test_get_synergies_parity() -> None:
    a = supabase_repo.get_synergies("Lulu", role="support")
    b = json_repo.get_synergies("Lulu", role="support")
    assert a["role"] == b["role"]
    assert a["base_winrate"] == pytest.approx(b["base_winrate"])
    assert a["base_wilson"] == pytest.approx(b["base_wilson"])
    _assert_rows_equal(a["rows"], b["rows"], keys=("mate_key",))
