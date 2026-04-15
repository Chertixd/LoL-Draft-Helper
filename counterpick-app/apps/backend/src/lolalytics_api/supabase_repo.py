import math
from typing import Any, Dict, List, Optional, Tuple
from lolalytics_api.supabase_client import get_supabase_client


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


def _champion_map() -> Dict[str, Tuple[str, str]]:
    """
    Returns mapping slug -> (key, name) and key -> name for quick lookups.
    """
    supabase = get_supabase_client()
    res = supabase.table("champions").select("key,name").execute()
    slug_map: Dict[str, Tuple[str, str]] = {}
    key_to_name: Dict[str, str] = {}
    for row in res.data or []:
        key = row["key"]
        name = row["name"]
        slug = _normalize_slug(name)
        slug_map[slug] = (key, name)
        key_to_name[key] = name
    return {"slug_map": slug_map, "key_to_name": key_to_name}


def _get_latest_patch(fallback: Optional[str] = None) -> str:
    supabase = get_supabase_client()
    res = (
        supabase.table("patches")
        .select("patch,created_at")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["patch"]
    if fallback:
        return fallback
    raise RuntimeError("No patch found in Supabase.")


def _resolve_champion(champion: str) -> Tuple[str, str]:
    maps = _champion_map()
    slug_map = maps["slug_map"]
    key_to_name = maps["key_to_name"]
    slug = _normalize_slug(champion)
    if slug in slug_map:
        key, name = slug_map[slug]
        return key, name
    # Fallback: direct key lookup
    if champion in key_to_name:
        return champion, key_to_name[champion]
    raise ValueError(f"Champion '{champion}' not found in Supabase.")


def _determine_role(
    champion_key: str, patch: str, requested_role: Optional[str]
) -> str:
    if requested_role:
        return requested_role
    supabase = get_supabase_client()
    res = (
        supabase.table("champion_stats")
        .select("role,games")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .order("games", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["role"]
    raise ValueError(f"No stats found for champion {champion_key} and patch {patch}.")


def _attach_names(
    rows: List[Dict[str, Any]], key_to_name: Dict[str, str], key_field: str
) -> List[Dict[str, Any]]:
    for row in rows:
        target_key = row.get(key_field)
        row["name"] = key_to_name.get(target_key, target_key)
    return rows


def get_champion_stats(
    champion: str, role: Optional[str] = None, patch: Optional[str] = None
) -> Dict[str, Any]:
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    champion_key, champion_name = _resolve_champion(champion)
    role = _determine_role(champion_key, patch, role)

    res = (
        supabase.table("champion_stats")
        .select("*")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .eq("role", role)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise RuntimeError(
            f"No champion_stats row for champion={champion}, role={role}, patch={patch}"
        )
    row = res.data[0]
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
            "rows": [...],
            "base_winrate": float,
            "base_wilson": float,
            "role": str
        }
    """
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    champion_key, _ = _resolve_champion(champion)
    role = _determine_role(champion_key, patch, role)
    # Default: opponent_role = eigene Rolle (Support vs Support, etc.)
    opponent_role = opponent_role or role

    # Hole Gesamtstatistiken des Champions für diese Rolle (games UND wins)
    stats_res = (
        supabase.table("champion_stats")
        .select("games, wins")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .eq("role", role)
        .limit(1)
        .execute()
    )
    base_games = stats_res.data[0]["games"] if stats_res.data else 0
    base_wins = stats_res.data[0]["wins"] if stats_res.data else 0
    base_winrate = base_wins / base_games if base_games > 0 else 0.5
    base_wilson = _wilson_score(base_wins, base_games, z=1.44)
    
    # Hole alle Champion-Stats für die Gegner-Rolle (für Gegner-Base-WR)
    opponent_stats_res = (
        supabase.table("champion_stats")
        .select("champion_key, games, wins")
        .eq("patch", patch)
        .eq("role", opponent_role)
        .execute()
    )
    opponent_stats_map = {
        r["champion_key"]: {"games": r["games"] or 0, "wins": r["wins"] or 0}
        for r in opponent_stats_res.data or []
    }
    total_role_games = sum(s["games"] for s in opponent_stats_map.values())

    res = (
        supabase.table("matchups")
        .select("*")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .eq("role", role)
        .eq("opponent_role", opponent_role)
        .execute()
    )
    rows = res.data or []

    # Filter nach prozentualem Minimum an Matchup-Games (relativ zu Champion-Gesamtspielen)
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
        row["opponent_base_wr"] = opp_wins / opp_games if opp_games > 0 else 0.5
        
        # normalized_delta nur bei gültigen Gegner-Stats berechnen
        if opp_games > 0:
            opp_wilson = _wilson_score(opp_wins, opp_games, z=1.44)
            # Erwartete WR gegen diesen Gegner = 1 - Gegner Base WR
            expected_wilson = 1 - opp_wilson
            row["normalized_delta"] = row["wilson_score"] - expected_wilson
        else:
            row["normalized_delta"] = None  # Keine gültigen Gegner-Stats
        
        # Füge Opponent Pickrate hinzu für Debug/Anzeige
        row["opponent_pickrate"] = opp_games / total_role_games if total_role_games > 0 else 0
    
    # Attach opponent names
    key_to_name = _champion_map()["key_to_name"]
    rows = _attach_names(rows, key_to_name, "opponent_key")
    
    # Erstelle zwei sortierte Listen: nach Delta und nach Normalized Delta
    # Counter mich = negative Deltas, Ich countere = positive Deltas
    if ascending:
        # Counter mich: negative Deltas, sortiert aufsteigend (schlechteste zuerst)
        rows_by_delta = sorted([r for r in rows if r["delta"] < 0], key=lambda r: r["delta"])
        rows_by_normalized = sorted(
            [r for r in rows if r["normalized_delta"] is not None and r["normalized_delta"] < 0],
            key=lambda r: r["normalized_delta"]
        )
    else:
        # Ich countere: positive Deltas, sortiert absteigend (beste zuerst)
        rows_by_delta = sorted([r for r in rows if r["delta"] > 0], key=lambda r: r["delta"], reverse=True)
        rows_by_normalized = sorted(
            [r for r in rows if r["normalized_delta"] is not None and r["normalized_delta"] > 0],
            key=lambda r: r["normalized_delta"],
            reverse=True
        )

    return {
        "by_delta": rows_by_delta[:limit],
        "by_normalized": rows_by_normalized[:limit],
        "base_winrate": base_winrate,
        "base_wilson": base_wilson,
        "role": role
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
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    champion_key, _ = _resolve_champion(champion)
    role = _determine_role(champion_key, patch, role)

    # Hole Gesamtstatistiken des Champions für diese Rolle (games UND wins)
    stats_res = (
        supabase.table("champion_stats")
        .select("games, wins")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .eq("role", role)
        .limit(1)
        .execute()
    )
    base_games = stats_res.data[0]["games"] if stats_res.data else 0
    base_wins = stats_res.data[0]["wins"] if stats_res.data else 0
    base_winrate = base_wins / base_games if base_games > 0 else 0.5
    base_wilson = _wilson_score(base_wins, base_games, z=1.44)
    
    min_games = int(base_games * min_games_pct)

    query = (
        supabase.table("synergies")
        .select("*")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .eq("role", role)
    )
    # Filter nach mate_role wenn angegeben
    if mate_role:
        query = query.eq("mate_role", mate_role)
    res = query.execute()
    rows = res.data or []

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
        "role": role
    }


def get_items(patch: Optional[str] = None) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    res = supabase.table("items").select("*").eq("patch", patch).execute()
    return res.data or []


def get_runes(patch: Optional[str] = None) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    res = supabase.table("runes").select("*").eq("patch", patch).execute()
    return res.data or []


def get_summoner_spells(patch: Optional[str] = None) -> List[Dict[str, Any]]:
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    res = (
        supabase.table("summoner_spells").select("*").eq("patch", patch).execute()
    )
    return res.data or []


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
    supabase = get_supabase_client()
    patch = patch or _get_latest_patch()
    champion_key, champion_name = _resolve_champion(champion)
    
    # Hole alle Rollen-Stats für diesen Champion
    res = (
        supabase.table("champion_stats")
        .select("role, games, wins")
        .eq("patch", patch)
        .eq("champion_key", champion_key)
        .execute()
    )
    
    # Konvertiere zu statsByRole Format
    stats_by_role = {
        "0": {"games": 0, "wins": 0},  # top
        "1": {"games": 0, "wins": 0},  # jungle
        "2": {"games": 0, "wins": 0},  # middle
        "3": {"games": 0, "wins": 0},  # bottom
        "4": {"games": 0, "wins": 0}   # support
    }
    
    role_mapping = {
        "top": "0",
        "jungle": "1",
        "middle": "2",
        "bottom": "3",
        "support": "4"
    }
    
    for row in res.data or []:
        role_name = row.get("role", "").lower()
        role_num = role_mapping.get(role_name)
        if role_num is not None:
            stats_by_role[role_num] = {
                "games": row.get("games", 0) or 0,
                "wins": row.get("wins", 0) or 0
            }
    
    return {
        "champion_key": champion_key,
        "champion_name": champion_name,
        "statsByRole": stats_by_role
    }





