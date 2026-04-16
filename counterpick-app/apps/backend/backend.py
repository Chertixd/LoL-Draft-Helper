"""
backend.py
Flask-Backend für lolalytics-api Integration
Bietet REST-API-Endpunkte mit Caching für bessere Performance
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from lolalytics_api import get_champion_data, get_tierlist, matchup, patch_notes
# Phase 2 CDN-02..08: json_repo replaces supabase_repo on the runtime path.
# The sb_* alias prefix is retained (D-22) so every downstream call site
# (/api/tierlist, /api/matchups, etc.) is unchanged. supabase_client +
# config imports are DROPPED — json_repo needs neither.
from lolalytics_api.json_repo import (
    get_champion_stats as sb_get_champion_stats,
    get_champion_stats_by_role as sb_get_champion_stats_by_role,
    get_items as sb_get_items,
    get_runes as sb_get_runes,
    get_summoner_spells as sb_get_summoner_spells,
    get_matchups as sb_get_matchups,
    get_synergies as sb_get_synergies,
    warm_cache as _json_repo_warm_cache,
    stale_status as _json_repo_stale_status,
    CDNError as _json_repo_CDNError,
    _table as _json_repo_table,
    _resolve_champion as _json_repo_resolve_champion,
    _get_latest_patch as _json_repo_get_latest_patch,
    _normalize_slug as _json_repo_normalize_slug,
)
from league_client_api import is_league_client_running, get_draft_picks_bans, get_draft_session, get_gameflow_session
from league_client_websocket import connect_to_league_client_websocket, disconnect_from_league_client_websocket, is_websocket_connected
import argparse
import json
import logging
import logging.handlers
import re
import sys
import time
import os
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from functools import wraps
import requests
from dotenv import load_dotenv

# Phase 1 SIDE-05 / D-14: path-resolution helpers. All runtime paths in this
# file route through these so the frozen-mode _MEIPASS contract and the
# platformdirs user-writable contract are both honored.
from lolalytics_api.resources import (
    LOL_DRAFT_APP_NAME,
    bundled_resource,
    user_cache_dir,
    user_log_dir,
)

# Import für Error Handling
try:
    import httpcore
    HTTPCORE_AVAILABLE = True
except ImportError:
    HTTPCORE_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

class LCUAuthFilter(logging.Filter):
    """Redacts LCU auth tokens from log records at write-time (LOG-05, D-13).

    Defense-in-depth: catches riot:<password> tokens at any call site,
    even if a developer adds a new logger.debug(url) that contains the token.
    """
    _pattern = re.compile(r'riot:[^\s"@]+', re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._pattern.sub('riot:[REDACTED]', str(record.msg))
        if record.args:
            record.args = tuple(
                self._pattern.sub('riot:[REDACTED]', a) if isinstance(a, str) else a
                for a in record.args
            )
        return True  # always pass — filter modifies, not suppresses


logger = logging.getLogger(__name__)


# Lade .env-Datei.
# Phase 1 D-14 / SIDE-05: path resolution routes through `bundled_resource`
# so neither the dunder-file anchor nor the current-working-directory helper
# appears on the runtime path. In dev mode this resolves to `apps/backend/.env`
# (via the resources
# helper's anchor walk); when frozen it resolves under `sys._MEIPASS`. The
# bundle spec does NOT include `.env`, so in frozen mode the file simply
# does not exist and `load_dotenv` becomes a no-op — correct behavior for
# the installed sidecar.
env_path = bundled_resource('.env')
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
CORS(app)  # Erlaube Cross-Origin Requests vom HTML-Frontend
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Persistenter JSON-Cache.
# Phase 1 D-14 / SIDE-05: the cache file lives under the platformdirs
# user_cache_dir() — on Windows %LOCALAPPDATA%\lol-draft-analyzer\Cache —
# so the frozen bundle's ephemeral _MEIPASS temp-extract never hosts
# runtime-mutable state. Phase 2 replaces this persistence path entirely
# with json_repo.py; for Phase 1 only the path-resolution mechanism
# changes (behavior is unchanged — read/write of cache_data.json).
CACHE_FILE = user_cache_dir() / 'cache_data.json'
CACHE_DURATION = 86400  # 24 Stunden in Sekunden

# Manuelle Rollen-Überschreibung (None = automatische Erkennung aktiv)
MANUAL_ROLE_OVERRIDE = None

# Synergy Role Mapping: Welche Rolle ist der primäre Synergie-Partner?
SYNERGY_ROLE_MAPPING = {
    'support': 'bottom',   # Support -> zeige ADCs
    'jungle': 'support',   # Jungle -> zeige Supports
    'middle': 'jungle',    # Mid -> zeige Jungler
    'bottom': 'support',   # ADC -> zeige Supports
    'top': 'jungle'        # Top -> zeige Jungler
}


def normalize_champion_name(name):
    """
    Normalisiert Champion-Namen für Lolalytics URLs
    Entfernt Apostrophe, Leerzeichen, Punkte und andere Sonderzeichen
    
    Beispiele:
        "Miss Fortune" -> "missfortune"
        "Kog'Maw" -> "kogmaw"
        "Kai'Sa" -> "kaisa"
        "Aurelion Sol" -> "aurelionsol"
    """
    normalized = name.lower()
    normalized = normalized.replace("'", "")
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace(".", "")
    return normalized


def normalize_patch(patch):
    """
    Normalisiert Patch-Version auf Major.Minor Format (z.B. "16.1.1" -> "16.1")
    """
    if not patch:
        return None
    parts = str(patch).split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return patch


def load_cache():
    """Lädt Cache aus JSON-Datei"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info("%d Einträge aus Cache-Datei geladen", len(data))
                return data
        except Exception as e:
            logger.error("Fehler beim Laden des Caches: %s", e)
            return {}
    return {}


def save_cache(cache_data):
    """Speichert Cache in JSON-Datei"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Fehler beim Speichern des Caches: %s", e)


# Lade existierenden Cache beim Start
cache = load_cache()


def cached(cache_key_func):
    """
    Decorator für Caching von API-Responses (persistent)
    cache_key_func: Funktion die den Cache-Key aus den Argumenten generiert
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generiere Cache-Key
            cache_key = cache_key_func(*args, **kwargs)
            
            # Prüfe ob im Cache und noch gültig
            if cache_key in cache:
                cached_data, timestamp = cache[cache_key]
                if time.time() - timestamp < CACHE_DURATION:
                    logger.debug("Cache HIT: %s", cache_key)
                    return cached_data
                else:
                    logger.debug("Cache EXPIRED: %s", cache_key)
                    del cache[cache_key]
                    save_cache(cache)

            # Nicht im Cache oder abgelaufen -> neu abrufen
            logger.info("Cache MISS: %s - Fetching from Lolalytics...", cache_key)
            result = func(*args, **kwargs)

            # Im Cache speichern
            cache[cache_key] = (result, time.time())
            save_cache(cache)  # Speichere nach jeder neuen Eintragung
            logger.debug("Cached: %s", cache_key)
            
            return result
        return wrapper
    return decorator


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Sidecar liveness probe.

    Consumed by:
      - the in-process probe thread (see `_probe_health_then_signal_ready`)
        which uses the first 200 here as the signal that it is safe to write
        the ready-file (Phase 1 SIDE-02 contract);
      - the Tauri host (Phase 3) as a secondary verification after the
        ready-file appears;
      - Plan 03's `test_backend_cli.py`, which asserts the `version` field
        is present.

    :return: JSON body ``{"status": "ok", "version": "<str>", ...}``. The
        `status` and `version` keys are load-bearing (Plan 03 test); extra
        diagnostic keys (service, cache_entries, timestamp) are retained
        for backward compatibility with the existing dev-mode usage.
    """
    # Phase 2 D-19: Phase 3 UX consumes `cached` to surface a per-table
    # staleness indicator. Empty dict is the fresh-startup state (warm_cache
    # has not written any 304/unreachable entries yet).
    _cached = _json_repo_stale_status()
    return jsonify({
        'status': 'ok',
        'version': '1.0.0-dev',
        'service': 'lolalytics-backend',
        'cache_entries': len(cache),
        'cached': _cached,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/primary-roles', methods=['GET'])
def get_primary_roles():
    """
    Gibt die primary_roles Konfiguration zurück
    """
    try:
        # Phase 1 D-14: resolve via bundled_resource (dev: anchored at
        # apps/backend/; frozen: under sys._MEIPASS). The champion_roles.json
        # file is shipped inside the lolalytics_api package source tree, and
        # the PyInstaller spec collects the package submodules so the file
        # lands at `_MEIPASS/src/lolalytics_api/champion_roles.json` in the
        # frozen bundle (matching the dev-mode layout).
        config_path = bundled_resource('src/lolalytics_api/champion_roles.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            primary_roles = config.get('primary_roles', {})
        return jsonify({
            'success': True,
            'primary_roles': primary_roles
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/patches', methods=['GET'])
def get_available_patches():
    """
    Gibt alle verfügbaren Patch-Versionen aus Supabase zurück
    Sortiert nach created_at DESC (neueste zuerst)
    """
    try:
        # Phase 2 CDN-08: read from the CDN-backed json_repo cache instead
        # of the direct Supabase client. Sort semantics match supabase_repo's
        # `order("created_at", desc=True)` — fall back to `patch` string sort
        # when created_at is missing, mirroring json_repo._get_latest_patch.
        patch_rows = list(_json_repo_table("patches"))
        patch_rows.sort(
            key=lambda r: (r.get("created_at") or "", r.get("patch") or ""),
            reverse=True,
        )
        patches = [row["patch"] for row in patch_rows]

        return jsonify({
            'success': True,
            'patches': patches
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/champion/<champion>', methods=['GET'])
def get_champion_info(champion):
    """
    Holt detaillierte Champion-Statistiken
    Query-Parameter:
        - lane: Lane (optional)
        - rank: Rang (default: emerald)
        - patch: Patch-Version (z.B. '15.23', '15.22', default: aktueller Patch)
    """
    try:
        lane = request.args.get('lane', '')
        rank = request.args.get('rank', 'emerald')
        patch = request.args.get('patch', '')
        
        # Normalisiere Champion-Namen (lowercase + Sonderzeichen entfernen)
        champion_normalized = normalize_champion_name(champion)
        
        # Cache-Key erstellen
        cache_key = f"champion_{champion_normalized}_{lane}_{rank}_{patch}"
        
        # Prüfe Cache
        if cache_key in cache:
            cached_data, timestamp = cache[cache_key]
            if time.time() - timestamp < CACHE_DURATION:
                logger.debug("Cache HIT: %s", cache_key)
                return jsonify(cached_data)
            else:
                logger.debug("Cache EXPIRED: %s", cache_key)
                del cache[cache_key]
                save_cache(cache)

        # Nicht im Cache - neu abrufen
        logger.info("Cache MISS: %s - Fetching from Lolalytics...", cache_key)
        
        # API-Aufruf (mit normalisiertem Namen)
        result_json = get_champion_data(champion=champion_normalized, lane=lane, rank=rank, patch=patch)
        result_data = json.loads(result_json)
        
        # Response-Dict erstellen
        response_dict = {
            'success': True,
            'champion': champion,  # Original-Name für Response
            'lane': lane,
            'rank': rank,
            'patch': patch if patch else 'current',
            'data': result_data
        }
        
        # Im Cache speichern (als Dict, nicht als Response-Objekt)
        cache[cache_key] = (response_dict, time.time())
        save_cache(cache)
        logger.debug("Cached: %s", cache_key)

        return jsonify(response_dict)
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Champion nicht gefunden: {champion}'
        }), 404
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tierlist', methods=['GET'])
@cached(lambda: f"tierlist_{request.args.get('lane', '')}_{request.args.get('rank', 'emerald')}_{request.args.get('n', '10')}_{request.args.get('patch', '')}")
def get_tier_list():
    """
    Holt die Tierlist für eine bestimmte Lane
    Query-Parameter:
        - lane: Lane (optional, default: alle)
        - rank: Rang (default: emerald)
        - n: Anzahl Champions (default: 10)
        - patch: Patch-Version (z.B. '15.23', '15.22', default: aktueller Patch)
    """
    try:
        lane = request.args.get('lane', '')
        rank = request.args.get('rank', 'emerald')
        n = int(request.args.get('n', 10))
        patch = request.args.get('patch', '')
        
        # Validierung
        if n < 1 or n > 50:
            return jsonify({'error': 'Parameter n muss zwischen 1 und 50 liegen'}), 400
        
        # API-Aufruf
        result_json = get_tierlist(n=n, lane=lane, rank=rank, patch=patch)
        result_data = json.loads(result_json)
        
        return jsonify({
            'success': True,
            'lane': lane,
            'rank': rank,
            'patch': patch if patch else 'current',
            'tierlist': result_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/matchup/<champ1>/<champ2>', methods=['GET'])
@cached(lambda champ1, champ2: f"matchup_{champ1.lower()}_{champ2.lower()}_{request.args.get('lane', '')}_{request.args.get('rank', 'emerald')}_{request.args.get('patch', '')}")
def get_matchup_data(champ1, champ2):
    """
    Holt Matchup-Daten zwischen zwei Champions
    Query-Parameter:
        - lane: Lane (optional)
        - rank: Rang (default: emerald)
        - patch: Patch-Version (z.B. '15.23', '15.22', default: aktueller Patch)
    """
    try:
        lane = request.args.get('lane', '')
        rank = request.args.get('rank', 'emerald')
        patch = request.args.get('patch', '')
        
        # Normalisiere Champion-Namen (lowercase + Sonderzeichen entfernen)
        champ1_normalized = normalize_champion_name(champ1)
        champ2_normalized = normalize_champion_name(champ2)
        
        # API-Aufruf (mit normalisierten Namen)
        result_json = matchup(champion1=champ1_normalized, champion2=champ2_normalized, lane=lane, rank=rank, patch=patch)
        result_data = json.loads(result_json)
        
        return jsonify({
            'success': True,
            'champion1': champ1,  # Original-Namen für Response
            'champion2': champ2,
            'lane': lane,
            'rank': rank,
            'patch': patch if patch else 'current',
            'matchup': result_data
        })
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Champion nicht gefunden'
        }), 404
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/patch-notes', methods=['GET'])
@cached(lambda: f"patch_notes_{request.args.get('category', 'all')}_{request.args.get('rank', 'emerald')}")
def get_patch_notes_data():
    """
    Holt Patch-Notes (gebuffte/generfed/angepasste Champions)
    Query-Parameter:
        - category: buffed, nerfed, adjusted oder all (default: all)
        - rank: Rang (default: emerald)
    """
    try:
        category = request.args.get('category', 'all')
        rank = request.args.get('rank', 'emerald')
        
        # Validierung
        valid_categories = ['buffed', 'nerfed', 'adjusted', 'all']
        if category not in valid_categories:
            return jsonify({
                'error': f'Ungültige Kategorie. Erlaubt: {", ".join(valid_categories)}'
            }), 400
        
        # API-Aufruf
        result_json = patch_notes(category=category, rank=rank)
        result_data = json.loads(result_json)
        
        return jsonify({
            'success': True,
            'category': category,
            'rank': rank,
            'patch_notes': result_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/champion/<champion>/stats-by-role', methods=['GET'])
@cached(lambda champion: f"champion_stats_by_role_{champion.lower()}_{request.args.get('patch', '')}")
def get_champion_stats_by_role(champion):
    """
    Holt alle Rollen-Statistiken für einen Champion (für Role Predictor)
    Query-Parameter:
        - patch: Patch-Version (optional, default: aktueller Patch)
    """
    try:
        patch = request.args.get('patch', None)
        champion_normalized = normalize_champion_name(champion)
        
        result = sb_get_champion_stats_by_role(
            champion=champion_normalized,
            patch=patch
        )
        
        return jsonify({
            'success': True,
            'champion_key': result['champion_key'],
            'champion_name': result['champion_name'],
            'statsByRole': result['statsByRole'],
            'patch': patch or 'current'
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Champion nicht gefunden: {champion}'
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/champion/<champion>/role-probabilities', methods=['GET'])
@cached(lambda champion: f"champion_role_probabilities_{champion.lower()}_{request.args.get('patch', '')}")
def get_champion_role_probabilities(champion):
    """
    Berechnet Rollen-Wahrscheinlichkeiten für einen Champion basierend auf Spielanzahl pro Rolle.
    Query-Parameter:
        - patch: Patch-Version (optional, default: aktueller Patch)
    
    Returns:
        {
            "success": true,
            "champion_key": "Urgot",
            "champion_name": "Urgot",
            "probabilities": {
                "top": 0.85,
                "jungle": 0.02,
                "middle": 0.08,
                "bottom": 0.03,
                "support": 0.02
            },
            "totalGames": 50000,
            "gamesByRole": {
                "top": 42500,
                "jungle": 1000,
                ...
            }
        }
    """
    try:
        patch = request.args.get('patch', None)
        champion_normalized = normalize_champion_name(champion)
        
        result = sb_get_champion_stats_by_role(
            champion=champion_normalized,
            patch=patch
        )
        
        stats_by_role = result.get('statsByRole', {})
        
        # Rolle-Nummer zu Name Mapping
        role_num_to_name = {
            '0': 'top',
            '1': 'jungle',
            '2': 'middle',
            '3': 'bottom',
            '4': 'support'
        }
        
        # Berechne Total Games
        total_games = 0
        games_by_role = {}
        
        for role_num, role_data in stats_by_role.items():
            role_name = role_num_to_name.get(role_num, role_num)
            games = role_data.get('games', 0) or 0
            games_by_role[role_name] = games
            total_games += games
        
        # Berechne Wahrscheinlichkeiten
        probabilities = {}
        for role_name in ['top', 'jungle', 'middle', 'bottom', 'support']:
            if total_games > 0:
                probabilities[role_name] = round(games_by_role.get(role_name, 0) / total_games, 4)
            else:
                probabilities[role_name] = 0.2  # Gleichverteilung bei 0 Games
        
        return {
            'success': True,
            'champion_key': result['champion_key'],
            'champion_name': result['champion_name'],
            'probabilities': probabilities,
            'totalGames': total_games,
            'gamesByRole': games_by_role,
            'patch': patch or 'current'
        }
    except ValueError as e:
        # Bei Fehlern: Cache nicht nutzen, daher raise für @cached
        return {
            'success': False,
            'error': f'Champion nicht gefunden: {champion}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@app.route('/api/champions/role-probabilities', methods=['POST'])
def get_batch_role_probabilities():
    """
    Batch-Endpoint: Holt Rollen-Wahrscheinlichkeiten für mehrere Champions auf einmal.
    Effizienter als mehrere einzelne Requests.
    
    Request Body:
        {
            "champions": ["Urgot", "Gragas", "Jinx"],
            "patch": "15.24"  // optional
        }
    
    Returns:
        {
            "success": true,
            "results": {
                "Urgot": { "probabilities": {...}, "totalGames": ... },
                "Gragas": { "probabilities": {...}, "totalGames": ... },
                ...
            }
        }
    """
    try:
        request_data = request.get_json()
        
        if not request_data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        champions = request_data.get('champions', [])
        patch = request_data.get('patch', None)
        
        if not champions or not isinstance(champions, list):
            return jsonify({
                'success': False,
                'error': 'champions array is required'
            }), 400
        
        role_num_to_name = {
            '0': 'top',
            '1': 'jungle',
            '2': 'middle',
            '3': 'bottom',
            '4': 'support'
        }
        
        results = {}
        
        for champion in champions:
            try:
                champion_normalized = normalize_champion_name(champion)
                
                # Prüfe Cache
                cache_key = f"champion_role_probabilities_{champion_normalized}_{patch or ''}"
                if cache_key in cache:
                    cached_data, timestamp = cache[cache_key]
                    if time.time() - timestamp < CACHE_DURATION:
                        # Nutze cached Result
                        results[champion] = {
                            'probabilities': cached_data.get('probabilities', {}),
                            'totalGames': cached_data.get('totalGames', 0),
                            'gamesByRole': cached_data.get('gamesByRole', {})
                        }
                        continue
                
                result = sb_get_champion_stats_by_role(
                    champion=champion_normalized,
                    patch=patch
                )
                
                stats_by_role = result.get('statsByRole', {})
                
                total_games = 0
                games_by_role = {}
                
                for role_num, role_data in stats_by_role.items():
                    role_name = role_num_to_name.get(role_num, role_num)
                    games = role_data.get('games', 0) or 0
                    games_by_role[role_name] = games
                    total_games += games
                
                probabilities = {}
                for role_name in ['top', 'jungle', 'middle', 'bottom', 'support']:
                    if total_games > 0:
                        probabilities[role_name] = round(games_by_role.get(role_name, 0) / total_games, 4)
                    else:
                        probabilities[role_name] = 0.2
                
                results[champion] = {
                    'probabilities': probabilities,
                    'totalGames': total_games,
                    'gamesByRole': games_by_role
                }
                
                # Cache speichern
                cache[cache_key] = ({
                    'probabilities': probabilities,
                    'totalGames': total_games,
                    'gamesByRole': games_by_role
                }, time.time())
                
            except Exception as e:
                logger.warning("Fehler beim Laden der Wahrscheinlichkeiten für %s: %s", champion, e)
                results[champion] = {
                    'error': str(e),
                    'probabilities': {'top': 0.2, 'jungle': 0.2, 'middle': 0.2, 'bottom': 0.2, 'support': 0.2},
                    'totalGames': 0
                }
        
        # Speichere Cache
        save_cache(cache)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.error("Fehler in /api/champions/role-probabilities: %s", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/champion/<champion>/matchups', methods=['GET'])
def get_champion_matchups(champion):
    """
    Holt Matchup-Daten für einen Champion aus der Supabase Datenbank.
    
    Query-Parameter:
        - role: Rolle (optional, default: meistgespielte Rolle)
        - patch: Patch-Version (optional, default: aktueller Patch)
        - limit: Anzahl Ergebnisse pro Liste (default: 10)
    
    Returns:
        {
            "success": true,
            "champion": "Thresh",
            "role": "support",
            "counters_against_me": [...],  # Champions die mich countern (niedrige WR)
            "i_counter": [...]              # Champions die ich countere (hohe WR)
        }
    """
    try:
        role = request.args.get('role', None)
        patch = request.args.get('patch', None)
        limit = int(request.args.get('limit', 10))
        # Prozentuales Minimum an Matchup-Games (Standard: 0.3% = 0.003)
        min_games_pct = float(request.args.get('min_games_pct', 0.003))
        
        champion_normalized = normalize_champion_name(champion)
        
        # Hole Matchups - aufsteigend sortiert (schlechteste zuerst = counters against me)
        # opponent_role=role bedeutet: Support vs Support, Top vs Top, etc.
        # min_games_pct filtert Quatschpicks mit zu wenig Spielen (relativ zur Gesamtspielzahl)
        # Gibt jetzt Dict mit by_delta, by_normalized, base_winrate, base_wilson, role zurück
        counters_result = sb_get_matchups(
            champion=champion_normalized,
            role=role,
            opponent_role=role,  # Gleiche Rolle wie eigene (z.B. Support vs Support)
            patch=patch,
            limit=limit,
            ascending=True,  # Negative Deltas (Counter mich)
            min_games_pct=min_games_pct
        )
        
        # Hole Matchups - absteigend sortiert (beste zuerst = I counter them)
        i_counter_result = sb_get_matchups(
            champion=champion_normalized,
            role=role,
            opponent_role=role,  # Gleiche Rolle wie eigene
            patch=patch,
            limit=limit,
            ascending=False,  # Positive Deltas (Ich countere)
            min_games_pct=min_games_pct
        )
        
        # Extrahiere Daten aus den Ergebnissen
        used_role = counters_result.get('role') or i_counter_result.get('role') or role
        base_winrate = counters_result.get('base_winrate', 0)
        base_wilson = counters_result.get('base_wilson', 0)
        
        return jsonify({
            'success': True,
            'champion': champion,
            'role': used_role,
            'patch': patch or 'current',
            'base_winrate': base_winrate,
            'base_wilson': base_wilson,
            # Zwei Listen pro Kategorie: sortiert nach Delta und nach Normalized Delta
            'counters_by_delta': counters_result.get('by_delta', []),
            'counters_by_normalized': counters_result.get('by_normalized', []),
            'i_counter_by_delta': i_counter_result.get('by_delta', []),
            'i_counter_by_normalized': i_counter_result.get('by_normalized', [])
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Champion nicht gefunden: {champion}'
        }), 404
    except Exception as e:
        logger.error("Fehler in /api/champion/%s/matchups: %s", champion, e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/champion/<champion>/synergies', methods=['GET'])
def get_champion_synergies(champion):
    """
    Holt Synergie-Daten für einen Champion aus der Supabase Datenbank.
    Verwendet das Synergy Role Mapping um die relevantesten Partner zu zeigen.
    
    Query-Parameter:
        - role: Rolle des Champions (optional, default: meistgespielte Rolle)
        - patch: Patch-Version (optional, default: aktueller Patch)
        - limit: Anzahl Ergebnisse (default: 10)
        - mate_role: Rolle der Synergie-Partner (optional, default: aus Mapping)
    
    Returns:
        {
            "success": true,
            "champion": "Thresh",
            "role": "support",
            "mate_role": "bottom",
            "synergies": [...]  # Beste Synergie-Partner (hohe WR)
        }
    """
    try:
        role = request.args.get('role', None)
        patch = request.args.get('patch', None)
        limit = int(request.args.get('limit', 10))
        # Prozentualer Anteil der Gesamtspiele (0.3% = 0.003)
        min_games_pct = float(request.args.get('min_games_pct', 0.003))
        mate_role = request.args.get('mate_role', None)
        
        champion_normalized = normalize_champion_name(champion)
        
        # Ermittle die Rolle des Champions wenn nicht angegeben
        used_role = role
        if not used_role:
            # Phase 2 CDN-08: resolve the most-played role from the CDN-backed
            # champion_stats cache instead of a direct supabase query. Mirrors
            # the original "order games desc limit 1" semantics.
            champion_key, _ = _json_repo_resolve_champion(champion_normalized)
            current_patch = patch or _json_repo_get_latest_patch()
            role_rows = [
                r
                for r in _json_repo_table("champion_stats")
                if r.get("patch") == current_patch
                and r.get("champion_key") == champion_key
            ]
            if role_rows:
                role_rows.sort(key=lambda r: r.get("games", 0) or 0, reverse=True)
                used_role = role_rows[0].get("role")
        
        # Bestimme mate_role aus Mapping wenn nicht explizit angegeben
        if not mate_role and used_role:
            mate_role = SYNERGY_ROLE_MAPPING.get(used_role.lower(), None)
        
        # Hole Synergien direkt mit mate_role Filter aus der Datenbank
        # min_games_pct filtert Quatschpicks mit zu wenig Spielen (relativ zur Gesamtspielzahl)
        # Gibt jetzt Dict mit rows, base_winrate, base_wilson, role zurück
        synergies_result = sb_get_synergies(
            champion=champion_normalized,
            role=used_role,
            mate_role=mate_role,
            patch=patch,
            limit=limit,
            min_games_pct=min_games_pct
        )
        
        # Extrahiere Daten aus dem Ergebnis
        actual_role = synergies_result.get('role') or used_role
        base_winrate = synergies_result.get('base_winrate', 0)
        base_wilson = synergies_result.get('base_wilson', 0)
        
        return jsonify({
            'success': True,
            'champion': champion,
            'role': actual_role,
            'mate_role': mate_role,
            'patch': patch or 'current',
            'base_winrate': base_winrate,
            'base_wilson': base_wilson,
            'synergies': synergies_result.get('rows', [])
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Champion nicht gefunden: {champion}'
        }), 404
    except Exception as e:
        logger.error("Fehler in /api/champion/%s/synergies: %s", champion, e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/champions/list', methods=['GET'])
def get_champions_list():
    """
    Gibt Liste aller Champion-Namen zurück (für Auto-Complete)
    """
    champions = [
        "Aatrox", "Ahri", "Akali", "Akshan", "Alistar", "Ambessa", "Amumu", "Anivia", "Annie",
        "Aphelios", "Ashe", "Aurelion Sol", "Aurora", "Azir", "Bard", "Bel'Veth", "Blitzcrank",
        "Brand", "Briar", "Braum", "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath", "Corki",
        "Darius", "Diana", "Dr. Mundo", "Draven", "Ekko", "Elise", "Evelynn", "Ezreal",
        "Fiddlesticks", "Fiora", "Fizz", "Galio", "Gangplank", "Garen", "Gnar", "Gragas",
        "Graves", "Gwen", "Hecarim", "Heimerdinger", "Hwei", "Illaoi", "Irelia", "Ivern",
        "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx", "K'Sante", "Kai'Sa",
        "Kalista", "Karma", "Karthus", "Kassadin", "Katarina", "Kayle", "Kayn", "Kennen",
        "Kha'Zix", "Kindred", "Kled", "Kog'Maw", "LeBlanc", "Lee Sin", "Leona", "Lillia",
        "Lissandra", "Lucian", "Lulu", "Lux", "Malphite", "Malzahar", "Maokai", "Master Yi",
        "Mel", "Milio", "Miss Fortune", "Mordekaiser", "Morgana", "Naafiri", "Nami", "Nasus",
        "Nautilus", "Neeko", "Nilah", "Nidalee", "Nocturne", "Nunu & Willump", "Olaf", "Orianna",
        "Ornn", "Pantheon", "Poppy", "Pyke", "Qiyana", "Quinn", "Rakan", "Rammus",
        "Rek'Sai", "Rell", "Renata Glasc", "Renekton", "Rengar", "Riven", "Rumble",
        "Ryze", "Samira", "Sejuani", "Senna", "Seraphine", "Sett", "Shaco", "Shen",
        "Shyvana", "Singed", "Sion", "Sivir", "Skarner", "Smolder", "Sona", "Soraka",
        "Swain", "Sylas", "Syndra", "Tahm Kench", "Taliyah", "Talon", "Taric", "Teemo",
        "Thresh", "Tristana", "Trundle", "Tryndamere", "Twisted Fate", "Twitch", "Udyr",
        "Urgot", "Varus", "Vayne", "Veigar", "Vel'Koz", "Vex", "Vi", "Viego", "Viktor",
        "Vladimir", "Volibear", "Warwick", "Wukong", "Xayah", "Xerath", "Xin Zhao",
        "Yasuo", "Yone", "Yorick", "Yunara", "Yuumi", "Zac", "Zaheen", "Zed", "Zeri", "Ziggs", "Zilean",
        "Zoe", "Zyra"
    ]
    
    return jsonify({
        'success': True,
        'champions': champions,
        'count': len(champions)
    })


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Leert den gesamten Cache (nur für Testing/Debug)"""
    global cache
    old_size = len(cache)
    cache = {}
    save_cache(cache)  # Lösche auch die Datei
    if CACHE_FILE.exists():
        os.remove(CACHE_FILE)
    return jsonify({
        'success': True,
        'message': f'{old_size} Cache-Einträge gelöscht'
    })


@app.route('/api/champion-name-to-key', methods=['POST'])
def champion_name_to_key():
    """
    Konvertiert Champion-Namen zu Supabase champion_key
    Request Body: { "championNames": ["Jinx", "Caitlyn", ...] }
    Response: { "success": true, "mapping": {"Jinx": "Jinx", "Caitlyn": "Caitlyn", ...} }
    """
    try:
        request_data = request.get_json()
        champion_names = request_data.get('championNames', [])
        
        if not champion_names or not isinstance(champion_names, list):
            return jsonify({
                'success': False,
                'error': 'championNames array required'
            }), 400
        
        # Phase 2 CDN-08: use json_repo's identical-signature helpers instead
        # of supabase_repo. Both modules ship the same _resolve_champion +
        # _normalize_slug contract (copied verbatim — see json_repo.py
        # docstring).
        result = {}
        for name in champion_names:
            try:
                normalized = _json_repo_normalize_slug(name)
                key, _ = _json_repo_resolve_champion(normalized)
                result[name] = key
            except Exception as e:
                # Champion nicht gefunden - verwende normalisierten Namen als Fallback
                result[name] = normalized
                logger.warning("Champion '%s' nicht gefunden, verwende '%s' als Key", name, normalized)
        
        return jsonify({
            'success': True,
            'mapping': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_current_role(session):
    """
    Ermittelt die Rolle des lokalen Spielers sicher aus der Session.
    Extrahiert die Rolle aus dem /lol-champ-select/v1/session JSON.
    Implementiert nach Draftgap-Methode: Nutzt localPlayerCellId und assignedPosition.
    
    Args:
        session: Dictionary mit Session-Daten von der LCU API
        
    Returns:
        str: Die erkannte Rolle ('top', 'jungle', 'middle', 'bottom', 'support')
    """
    if not session or not isinstance(session, dict):
        logger.error("Session ist leer oder kein Dictionary")
        return 'top'

    # Debug: Zeige Session-Struktur
    timer_phase = session.get('timer', {}).get('phase', 'UNKNOWN')
    logger.debug("Draft-Phase: %s", timer_phase)

    # 1. Finde die localPlayerCellId
    local_cell_id = session.get('localPlayerCellId')
    if local_cell_id is None:
        logger.error("localPlayerCellId nicht in Session gefunden")
        return 'top'  # Fallback

    logger.debug("LocalPlayerCellId: %s", local_cell_id)

    # 2. Suche den Spieler im myTeam Array anhand der cellId
    my_team = session.get('myTeam', [])
    if not my_team:
        logger.error("myTeam ist leer")
        return 'top'

    logger.debug("myTeam hat %d Spieler", len(my_team))

    # Finde den Spieler mit matching cellId
    me = None
    for i, player in enumerate(my_team):
        if isinstance(player, dict):
            cell_id = player.get('cellId')
            assigned_pos = player.get('assignedPosition', '')
            summoner_id = player.get('summonerId', '')
            logger.debug("Player %d: cellId=%s, assignedPosition='%s', summonerId=%s", i, cell_id, assigned_pos, summoner_id)
            if cell_id == local_cell_id:
                me = player
                logger.debug("Lokaler Spieler gefunden bei Index %d", i)
                break

    if not me:
        available_cell_ids = [p.get('cellId') for p in my_team if isinstance(p, dict)]
        logger.error("Spieler mit CellId %s nicht in myTeam gefunden. Verfügbare CellIds: %s", local_cell_id, available_cell_ids)
        return 'top'

    # 3. Lese assignedPosition aus (wie Draftgap)
    assigned_position = me.get('assignedPosition', '')

    # Debug: Zeige alle verfügbaren Felder des Spielers
    logger.debug("Spieler-Daten: %s", list(me.keys()))

    if not assigned_position or assigned_position == '':
        logger.warning("assignedPosition ist leer/None für CellId %s", local_cell_id)
        logger.warning("Mögliche Gründe: 1) Noch nicht zugewiesen, 2) Blind Pick, 3) Frühe Draft-Phase")
        logger.warning("Draft-Phase: %s", timer_phase)

        # Alternative: Versuche Rolle aus Actions zu extrahieren
        # In Draftgap wird die Rolle auch aus den Actions gelesen, wenn assignedPosition leer ist
        actions = session.get('actions', [])
        if actions:
            logger.debug("Versuche Rolle aus Actions zu extrahieren...")
            # Actions ist ein Array von Arrays - jede Runde hat ein Array von Actions
            for action_round in actions:
                if isinstance(action_round, list):
                    for action in action_round:
                        if isinstance(action, dict):
                            actor_cell_id = action.get('actorCellId')
                            action_type = action.get('type', '')
                            # Wenn es eine Pick-Action für unseren CellId ist
                            if actor_cell_id == local_cell_id and action_type == 'pick':
                                # Leider haben Actions keine direkte Rolle, aber wir können prüfen
                                # ob es eine completed Action gibt, die auf eine Rolle hinweist
                                logger.debug("Pick-Action gefunden für CellId %s", local_cell_id)

        # In frühen Phasen kann assignedPosition noch leer sein
        # Prüfe ob wir in einer Phase sind, wo Rollen normalerweise schon zugewiesen sind
        if timer_phase in ['PLANNING', 'BAN_PICK']:
            logger.warning("In Phase %s - Rolle sollte normalerweise zugewiesen sein", timer_phase)

        return 'top'  # Fallback

    raw_role = str(assigned_position).lower().strip()
    logger.debug("API Raw assignedPosition: '%s' | CellID: %s", raw_role, local_cell_id)
    
    # 4. Mapping der Riot-Begriffe auf Standard-Begriffe (wie Draftgap)
    # Draftgap verwendet: top, jungle, bottom, middle, utility -> support
    role_map = {
        'top': 'top',
        'jungle': 'jungle',
        'middle': 'middle',
        'mid': 'middle',
        'bottom': 'bottom',  # ADC
        'utility': 'support',  # Support (wie Draftgap)
        'invalid': 'top',  # Fallback für invalid
        '': 'top'  # Fallback für leere Strings
    }
    
    detected_role = role_map.get(raw_role, 'top')
    
    if detected_role == 'top' and raw_role not in ['top', 'invalid', '']:
        logger.warning("Unbekannte Rolle '%s' -> Fallback zu 'top'", raw_role)

    logger.info("Rolle erkannt: '%s' -> '%s' (CellID: %s, Phase: %s)", raw_role, detected_role, local_cell_id, timer_phase)
    return detected_role


# ============================================================
# LEAGUE CLIENT API ROUTES
# ============================================================

@app.route('/api/league-client/status', methods=['GET'])
def get_league_client_status():
    """
    Prüft ob der League Client läuft und erreichbar ist.
    """
    try:
        client_running = is_league_client_running()
        return jsonify({
            'success': True,
            'client_running': client_running
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'client_running': False,
            'error': str(e)
        })


@app.route('/api/league-client/draft', methods=['GET'])
def get_league_client_draft():
    """
    Holt die aktuellen Draft-Daten (Champion Select).
    """
    try:
        if not is_league_client_running():
            return jsonify({
                'success': False,
                'error': 'League Client nicht verbunden'
            }), 503
        
        draft_data = get_draft_picks_bans()
        if draft_data:
            return jsonify({
                'success': True,
                'draft': draft_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Keine Draft-Session aktiv'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/league-client/session', methods=['GET'])
def get_league_client_session():
    """
    Holt die aktuelle Gameflow-Session.
    """
    try:
        if not is_league_client_running():
            return jsonify({
                'success': False,
                'error': 'League Client nicht verbunden'
            }), 503
        
        session_data = get_gameflow_session()
        if session_data:
            return jsonify({
                'success': True,
                'session': session_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Keine Session aktiv'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/set-role', methods=['POST'])
def set_role():
    """
    Setzt eine manuelle Rollen-Überschreibung für die automatische Erkennung.
    
    Request Body:
        {
            "role": "support"  # "top", "jungle", "middle", "bottom", "support", oder null/"auto" zum Deaktivieren
        }
    """
    global MANUAL_ROLE_OVERRIDE
    
    try:
        request_data = request.get_json()
        
        if not request_data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        role = request_data.get('role')
        
        # Valid roles
        valid_roles = ['top', 'jungle', 'middle', 'bottom', 'support']
        
        # Check if role should be disabled (null or "auto")
        if role is None or (isinstance(role, str) and role.lower() == 'auto'):
            MANUAL_ROLE_OVERRIDE = None
            logger.info("Manuelle Rollen-Überschreibung deaktiviert (automatische Erkennung aktiv)")
            return jsonify({
                'success': True,
                'role': 'auto',
                'message': 'Manual role override disabled. Auto-detection enabled.'
            })
        
        # Validate role
        if not isinstance(role, str):
            return jsonify({
                'success': False,
                'error': f'Role must be a string. Valid values: {valid_roles}, null, or "auto"'
            }), 400
        
        role_lower = role.lower()
        if role_lower not in valid_roles:
            return jsonify({
                'success': False,
                'error': f'Invalid role: "{role}". Valid values: {valid_roles}, null, or "auto"'
            }), 400
        
        # Set the override
        MANUAL_ROLE_OVERRIDE = role_lower
        logger.info("Manuelle Rollen-Überschreibung gesetzt: '%s'", MANUAL_ROLE_OVERRIDE)
        return jsonify({
            'success': True,
            'role': MANUAL_ROLE_OVERRIDE,
            'message': f'Manual role override set to: {MANUAL_ROLE_OVERRIDE}'
        })
        
    except Exception as e:
        logger.error("Fehler in /api/set-role: %s", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """
    Recommendation Engine: Berechnet optimale Champion-Picks basierend auf Matchups, Synergien und Rollen-Importance
    
    Request Body:
        {
            "myRole": "bottom",  # Optional: wird automatisch aus Session ermittelt wenn nicht angegeben
            "myTeam": [{"championKey": "Jinx", "role": "bottom"}],
            "enemyTeam": [{"championKey": "Caitlyn", "role": "bottom"}],
            "patch": "15.24",
            "isBlindPick": false
        }
    """
    try:
        from recommendation_engine import get_recommendations as calculate_recommendations
        
        request_data = request.get_json()
        
        if not request_data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        # Validiere erforderliche Felder
        if 'myTeam' not in request_data or 'enemyTeam' not in request_data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: myTeam, enemyTeam'
            }), 400
        
        # Extrahiere Parameter
        my_role = request_data.get('myRole')
        my_team = request_data.get('myTeam', [])
        enemy_team = request_data.get('enemyTeam', [])
        patch = normalize_patch(request_data.get('patch', ''))
        is_blind_pick = request_data.get('isBlindPick', False)
        
        # Rollen-Erkennung mit Priorität:
        # 1. Manuelle Überschreibung (höchste Priorität)
        # 2. Frontend-Request
        # 3. Automatische Erkennung aus Session
        # 4. Fallback zu 'top'
        
        if MANUAL_ROLE_OVERRIDE is not None:
            my_role = MANUAL_ROLE_OVERRIDE
            logger.info("Verwende manuelle Rollen-Überschreibung: '%s'", my_role)
        elif my_role:
            # Verwende Rolle aus Frontend-Request
            logger.info("Verwende Rolle aus Frontend-Request: '%s'", my_role)
        else:
            # Automatische Erkennung aus Session
            logger.info("Keine Rolle im Request - versuche automatische Erkennung aus Session...")
            session_data = get_draft_session()
            if session_data:
                detected_role = get_current_role(session_data)
                if detected_role:
                    my_role = detected_role
                    logger.info("Rolle automatisch aus Session ermittelt: '%s'", my_role)
                else:
                    logger.warning("Konnte Rolle nicht aus Session ermitteln")
            else:
                logger.info("Keine Draft-Session verfügbar")

        # Stelle sicher, dass myRole gesetzt ist
        if not my_role:
            my_role = 'top'  # Letzter Fallback
            logger.info("Verwende Fallback-Rolle: '%s'", my_role)
        
        # Rufe Recommendation Engine auf mit Error Handling für DB-Verbindungsfehler
        try:
            result = calculate_recommendations(
                my_role=my_role,
                my_team=my_team,
                enemy_team=enemy_team,
                patch=patch if patch else None,
                is_blind_pick=is_blind_pick
            )
        except Exception as db_error:
            # Fange spezifische DB-Verbindungsfehler ab
            error_type = type(db_error).__name__
            error_msg = str(db_error)
            
            # Prüfe auf RemoteProtocolError (Server disconnected)
            if HTTPCORE_AVAILABLE and isinstance(db_error, httpcore.RemoteProtocolError):
                logger.error("Database connection error (httpcore.RemoteProtocolError): %s", error_msg)
                return jsonify({
                    'success': False,
                    'error': 'Database connection lost. Please try again.',
                    'error_type': 'RemoteProtocolError'
                }), 503  # Service Unavailable
            elif HTTPX_AVAILABLE and isinstance(db_error, httpx.RemoteProtocolError):
                logger.error("Database connection error (httpx.RemoteProtocolError): %s", error_msg)
                return jsonify({
                    'success': False,
                    'error': 'Database connection lost. Please try again.',
                    'error_type': 'RemoteProtocolError'
                }), 503
            elif 'Server disconnected' in error_msg or 'RemoteProtocolError' in error_type:
                logger.error("Database connection error: %s", error_msg)
                return jsonify({
                    'success': False,
                    'error': 'Database connection lost. Please try again.',
                    'error_type': error_type
                }), 503
            else:
                # Andere Fehler weiterwerfen für allgemeines Error Handling
                raise
        
        # Gebe Ergebnis zurück
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except requests.exceptions.RequestException as e:
        logger.error("Request exception in /api/recommendations: %s", e)
        return jsonify({
            'success': False,
            'error': f'Request failed: {str(e)}'
        }), 500
    except Exception as e:
        logger.error("Fehler in /api/recommendations: %s", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/cache/stats', methods=['GET'])
def cache_stats():
    """Zeigt Cache-Statistiken"""
    cache_info = []
    current_time = time.time()
    
    for key, (data, timestamp) in cache.items():
        age = current_time - timestamp
        remaining = CACHE_DURATION - age
        cache_info.append({
            'key': key,
            'age_seconds': round(age, 2),
            'remaining_seconds': round(remaining, 2),
            'expired': remaining <= 0
        })
    
    return jsonify({
        'total_entries': len(cache),
        'cache_duration': CACHE_DURATION,
        'entries': cache_info
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpunkt nicht gefunden'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Interner Serverfehler'}), 500


# WebSocket Event Handler
@socketio.on('connect')
def handle_connect():
    """Handler für WebSocket-Verbindung vom Frontend"""
    logger.info("Client verbunden: %s", request.sid)
    
    # Starte League Client WebSocket-Verbindung wenn noch nicht verbunden
    if not is_websocket_connected():
        # Starte in separatem Thread, um Blockierung zu vermeiden
        threading.Thread(target=start_league_client_websocket, daemon=True).start()
    
    # Sende initiale Draft-Daten wenn verfügbar (in separatem Thread)
    def send_initial_data():
        try:
            time.sleep(0.5)  # Kurz warten, damit Verbindung stabil ist
            draft_data = get_draft_picks_bans()
            if draft_data and (draft_data.get('team1_picks') or draft_data.get('team2_picks')):
                logger.info("Sende initiale Draft-Daten an neuen Client")
                socketio.emit('draft_update', {
                    'success': True,
                    'draft': draft_data
                })
            else:
                logger.info("Keine initialen Draft-Daten verfügbar (nicht in Draft-Phase)")
        except Exception as e:
            logger.error("Fehler beim Senden initialer Draft-Daten: %s", e)
            import traceback
            traceback.print_exc()
    
    threading.Thread(target=send_initial_data, daemon=True).start()


@socketio.on('disconnect')
def handle_disconnect():
    """Handler für WebSocket-Trennung vom Frontend"""
    logger.info("Client getrennt: %s", request.sid)


# HTTP-Polling als Fallback (wenn WebSocket nicht verfügbar)
_draft_polling_thread = None
_draft_polling_active = False

def poll_draft_data():
    """
    Pollt regelmäßig Draft-Daten über HTTP (Fallback wenn WebSocket nicht verfügbar)
    """
    global _draft_polling_active
    
    _draft_polling_active = True
    last_draft_state = None
    
    while _draft_polling_active:
        try:
            # Versuche Draft-Daten zu holen
            draft_data = get_draft_picks_bans()
            
            if draft_data:
                # Prüfe ob sich etwas geändert hat
                current_state = str(draft_data.get('team1_picks', [])) + str(draft_data.get('team2_picks', []))
                if current_state != last_draft_state:
                    last_draft_state = current_state
                    logger.info("Draft-Update: Team1=%d Picks, Team2=%d Picks", len(draft_data.get('team1_picks', [])), len(draft_data.get('team2_picks', [])))
                    
                    # Sende Update an Frontend
                    def send_update():
                        try:
                            socketio.emit('draft_update', {
                                'success': True,
                                'draft': draft_data
                            })
                        except Exception as e:
                            logger.error("Fehler beim Senden des Polling-Updates: %s", e)
                    
                    threading.Thread(target=send_update, daemon=True).start()
            
            time.sleep(1)  # Poll alle 1 Sekunde
            
        except Exception as e:
            # Fehler ist normal wenn Client nicht läuft oder nicht in Draft
            time.sleep(2)  # Warte länger bei Fehlern
    
    logger.info("Draft-Polling beendet")

# Letzter gesendeter Draft-State (für Vergleich)
_last_draft_state = None


def _get_locked_picks_signature(draft_data: dict) -> tuple:
    """
    Erstellt eine Signatur der locked picks für schnellen Vergleich.
    Gibt Tuple von (team1_locked, team2_locked, team1_bans, team2_bans) zurück.
    """
    if not draft_data:
        return ((), (), (), ())
    
    team1_locked = tuple(
        (p.get('championId'), p.get('champion'))
        for p in draft_data.get('team1_picks', [])
        if p.get('isLocked')
    )
    team2_locked = tuple(
        (p.get('championId'), p.get('champion'))
        for p in draft_data.get('team2_picks', [])
        if p.get('isLocked')
    )
    team1_bans = tuple(
        b.get('championId')
        for b in draft_data.get('team1_bans', [])
    )
    team2_bans = tuple(
        b.get('championId')
        for b in draft_data.get('team2_bans', [])
    )
    
    return (team1_locked, team2_locked, team1_bans, team2_bans)


def _has_draft_changed(new_draft: dict) -> bool:
    """
    Prüft ob sich der Draft tatsächlich geändert hat.
    Vergleicht nur locked picks und bans, nicht hovers.
    """
    global _last_draft_state
    
    if _last_draft_state is None:
        return True
    
    new_sig = _get_locked_picks_signature(new_draft)
    old_sig = _get_locked_picks_signature(_last_draft_state)
    
    return new_sig != old_sig


def handle_draft_event(event_data):
    """
    Callback für League Client WebSocket Events
    Sendet Draft-Updates an alle verbundenen Frontend-Clients
    NUR wenn sich Picks/Bans tatsächlich geändert haben.
    Verarbeitet auch Gameflow-Events für Draft-Reset.
    """
    global _last_draft_state
    
    try:
        # Parse Event-Daten
        if isinstance(event_data, dict):
            uri = event_data.get('uri', '')
            
            # Prüfe ob es ein Gameflow Phase Event ist (für Draft-Reset)
            if '/lol-gameflow/v1/gameflow-phase' in uri:
                data = event_data.get('data', {})
                # Gameflow kann als String oder Dict kommen
                phase = data if isinstance(data, str) else data.get('data', '')
                
                # Reset Draft-State wenn wir nicht mehr in Champion Select sind
                if phase in ['None', 'Lobby', 'Matchmaking', 'InProgress', 'EndOfGame', 'WaitingForStats']:
                    if _last_draft_state is not None:
                        logger.info("Gameflow-Phase: %s - Draft-State zurückgesetzt", phase)
                        _last_draft_state = None
                        # Sende Reset-Event an Frontend
                        def send_reset():
                            try:
                                socketio.emit('draft_reset', {'phase': phase})
                                logger.info("Draft-Reset an Frontend gesendet (Phase: %s)", phase)
                            except Exception as e:
                                logger.error("Fehler beim Senden des Reset-Events: %s", e)
                        threading.Thread(target=send_reset, daemon=True).start()
                return
            
            # Prüfe ob es ein Champion Select Update ist
            if '/lol-champ-select/v1/session' in uri:
                # Extrahiere Draft-Daten
                draft_data = get_draft_picks_bans()
                if draft_data:
                    # Prüfe ob sich etwas geändert hat
                    if not _has_draft_changed(draft_data):
                        # Keine Änderung - kein Update senden
                        return
                    
                    # Änderung erkannt - Update senden
                    team1_picks = draft_data.get('team1_picks', [])
                    team2_picks = draft_data.get('team2_picks', [])
                    
                    # Zähle locked picks für Logging
                    team1_locked = sum(1 for p in team1_picks if p.get('isLocked'))
                    team2_locked = sum(1 for p in team2_picks if p.get('isLocked'))
                    logger.info("Draft-Änderung erkannt: Team1=%d locked, Team2=%d locked", team1_locked, team2_locked)
                    
                    # Bestimme myTeam basierend auf localPlayerCellId
                    # cellIds 0-4 = Blue Side (team1), cellIds 5-9 = Red Side (team2)
                    session = draft_data.get('session')
                    if session:
                        local_cell_id = session.get('localPlayerCellId')
                        if local_cell_id is not None:
                            draft_data['myTeam'] = 0 if local_cell_id < 5 else 1
                            logger.info("Team-Erkennung: localPlayerCellId=%s -> myTeam=%s (%s Side)", local_cell_id, draft_data['myTeam'], 'Blue' if draft_data['myTeam'] == 0 else 'Red')
                        elif 'myTeam' not in draft_data:
                            draft_data['myTeam'] = 0  # Fallback
                        
                        # Ermittle myRole aus Session
                        my_role = get_current_role(session)
                        draft_data['myRole'] = my_role
                        logger.info("Rolle des lokalen Spielers: %s", my_role)
                    elif 'myTeam' not in draft_data:
                        draft_data['myTeam'] = 0  # Fallback wenn keine Session
                    
                    # Speichere neuen State
                    _last_draft_state = draft_data
                    
                    # Sende an alle verbundenen Clients (in separatem Thread)
                    def send_update():
                        try:
                            socketio.emit('draft_update', {
                                'success': True,
                                'draft': draft_data
                            })
                            logger.info("Draft-Update an Frontend gesendet")
                        except Exception as e:
                            logger.error("Fehler beim Senden des Updates: %s", e)
                    
                    threading.Thread(target=send_update, daemon=True).start()
    except Exception as e:
        logger.error("Fehler beim Verarbeiten des Draft-Events: %s", e)
        import traceback
        traceback.print_exc()


def reset_draft_state():
    """
    Setzt den Draft-State zurück (z.B. nach Game End).
    Sollte aufgerufen werden wenn eine neue Draft-Session beginnt.
    """
    global _last_draft_state
    _last_draft_state = None


# Polling-Thread für Lockfile-Erkennung
_lockfile_polling_thread = None
_lockfile_polling_active = False

def poll_for_lockfile():
    """
    Pollt regelmäßig nach der Lockfile und startet WebSocket-Verbindung wenn gefunden
    """
    global _lockfile_polling_active
    
    _lockfile_polling_active = True
    max_attempts = 60  # 60 Versuche = 5 Minuten (alle 5 Sekunden)
    attempt = 0
    
    while _lockfile_polling_active and attempt < max_attempts:
        try:
            from league_client_auth import get_league_client_info
            client_info = get_league_client_info()
            
            if client_info:
                logger.info("Lockfile gefunden! Starte WebSocket-Verbindung...")
                _lockfile_polling_active = False
                start_league_client_websocket()
                return
            
            attempt += 1
            if attempt % 12 == 0:  # Alle 60 Sekunden
                logger.info("Warte auf Lockfile... (%d Sekunden)", attempt * 5)
            
            time.sleep(5)  # Warte 5 Sekunden zwischen Versuchen
            
        except Exception as e:
            logger.error("Fehler beim Polling: %s", e)
            time.sleep(5)

    if attempt >= max_attempts:
        logger.warning("Lockfile-Polling beendet (Timeout nach 5 Minuten)")
        _lockfile_polling_active = False

def start_league_client_websocket():
    """
    Startet WebSocket-Verbindung zum League Client
    Falls Lockfile nicht verfügbar, nutze HTTP-Polling als Fallback
    """
    global _lockfile_polling_thread, _lockfile_polling_active, _draft_polling_thread, _draft_polling_active
    
    try:
        logger.info("Starte League Client WebSocket-Verbindung...")
        success = connect_to_league_client_websocket(handle_draft_event)
        if success:
            logger.info("League Client WebSocket-Verbindung erfolgreich gestartet")
            _lockfile_polling_active = False  # Stoppe Lockfile-Polling
            _draft_polling_active = False  # Stoppe HTTP-Polling (WebSocket ist besser)
            
            # Sende Status-Update an Frontend (in separatem Thread)
            def send_status():
                try:
                    socketio.emit('league_client_status', {
                        'connected': True,
                        'message': 'League Client verbunden (WebSocket)'
                    })
                except Exception as e:
                    logger.error("Fehler beim Senden des Status: %s", e)

            threading.Thread(target=send_status, daemon=True).start()
        else:
            # Lockfile nicht gefunden - nutze HTTP-Polling als Fallback
            logger.info("WebSocket nicht verfügbar - starte HTTP-Polling als Fallback...")
            
            # Starte HTTP-Polling wenn noch nicht aktiv
            if not _draft_polling_active:
                _draft_polling_thread = threading.Thread(target=poll_draft_data, daemon=True)
                _draft_polling_thread.start()
                logger.info("HTTP-Polling gestartet (prüft alle 1 Sekunde)")

            # Starte auch Lockfile-Polling (falls Client später startet)
            if not _lockfile_polling_active:
                _lockfile_polling_thread = threading.Thread(target=poll_for_lockfile, daemon=True)
                _lockfile_polling_thread.start()
                logger.info("Lockfile-Polling gestartet (prüft alle 5 Sekunden)")
            
            # Sende Status an Frontend (in separatem Thread)
            def send_status():
                try:
                    socketio.emit('league_client_status', {
                        'connected': True,
                        'message': 'HTTP-Polling aktiv (WebSocket nicht verfügbar)'
                    })
                except Exception as e:
                    logger.error("Fehler beim Senden des Status: %s", e)

            threading.Thread(target=send_status, daemon=True).start()
    except Exception as e:
        error_msg = f"Fehler beim Starten der League Client Verbindung: {e}"
        logger.error("%s", error_msg)
        import traceback
        traceback.print_exc()
        
        # Starte HTTP-Polling als Fallback
        if not _draft_polling_active:
            _draft_polling_thread = threading.Thread(target=poll_draft_data, daemon=True)
            _draft_polling_thread.start()
            logger.info("HTTP-Polling als Fallback gestartet")
        
        # Sende Fehler-Status an Frontend (in separatem Thread)
        def send_error():
            try:
                socketio.emit('league_client_status', {
                    'connected': True,
                    'message': 'HTTP-Polling aktiv (Fallback-Modus)'
                })
            except Exception as e:
                logger.error("Fehler beim Senden des Fehler-Status: %s", e)
        
        threading.Thread(target=send_error, daemon=True).start()


def _configure_logging(log_dir: Path) -> None:
    """
    Configure the root logger with a daily-rotating file handler.

    LOG-01: Structured log files in %APPDATA%/dev.till.lol-draft-analyzer/logs/.
    LOG-04: Rotated files named backend-YYYY-MM-DD.log (active file stays backend.log).
    LOG-05: LCUAuthFilter redacts riot:<password> tokens at write-time (D-13).

    :param log_dir: Directory to write ``backend.log`` into. Created
        if missing.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "backend.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    # Rename rotated files to backend-YYYY-MM-DD.log (LOG-04)
    handler.suffix = "%Y-%m-%d"
    handler.namer = lambda name: name.replace("backend.log.", "backend-") + ".log"
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # LCU auth redaction at write-time (LOG-05, D-13)
    root.addFilter(LCUAuthFilter())


def _atomic_write_ready_file(path: Path, payload: dict) -> None:
    """
    Write ``payload`` to ``path`` atomically via a sibling tempfile and
    ``os.replace``.

    ``os.replace`` is atomic on both Windows (NTFS, Python 3.3+) and
    POSIX, so a concurrent reader (Tauri host or the Plan 03 integration
    test) will see either the previous state or the final fully-written
    JSON — never a half-written file (Pitfall #2 / D-04).

    :param path: Final destination of the ready-file.
    :param payload: JSON-serializable dict (the per-D-04 shape is
        ``{"port", "pid", "ready_at"}``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)  # atomic on Windows NTFS + POSIX


def _probe_health_then_signal_ready(
    port: int,
    ready_file: Path | None,
    interval_s: float = 0.05,
    timeout_s: float = 5.0,
) -> None:
    """
    Background probe: poll ``/api/health`` until 200 or timeout.

    On the first 200 response, write the ready-file (if requested) and
    return. On timeout, log the failure and call ``os._exit(1)`` —
    ``sys.exit(1)`` would only raise ``SystemExit`` in this thread (the
    thread machinery absorbs it) while the main thread keeps running
    ``socketio.run``. ``os._exit`` terminates the whole process so the
    non-zero exit status reaches Tauri / the CI harness.

    The probe URL uses the literal ``127.0.0.1`` — never ``localhost``,
    which on some Windows configurations resolves to IPv6 first and the
    Flask-SocketIO threading server is bound to IPv4 only (Pitfall #8).

    :param port: Port the Flask server is binding to.
    :param ready_file: Path to write the ready JSON into; ``None`` to skip.
    :param interval_s: Polling interval (default 50 ms per D-03).
    :param timeout_s: Total budget for the probe (default 5 s per D-03).
    """
    log = logging.getLogger(__name__)
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=0.5)
            if r.status_code == 200:
                if ready_file is not None:
                    payload = {
                        "port": port,
                        "pid": os.getpid(),
                        "ready_at": datetime.now(timezone.utc).isoformat(),
                    }
                    _atomic_write_ready_file(ready_file, payload)
                log.info("[READY] port=%d pid=%d", port, os.getpid())
                return
        except requests.RequestException:
            # Server not accepting yet; fall through to sleep and retry.
            pass
        time.sleep(interval_s)
    log.error(
        "[READY] /api/health did not return 200 within %.1fs", timeout_s
    )
    # Force-exit: cannot raise SystemExit from a sub-thread, and socketio.run
    # is blocking the main thread for the server's lifetime.
    os._exit(1)


def main() -> None:
    """
    Sidecar entrypoint.

    Lifecycle (Phase 1 SIDE-01 / SIDE-02 contract):

    1. Parse ``--port``, ``--ready-file``, ``--cache-dir``, ``--log-dir``.
    2. Configure rotating file logging under the resolved log dir.
    3. Point ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` at the bundled
       ``certifi/cacert.pem`` when it exists (frozen mode only — dev
       mode falls back to the pip-installed certifi automatically).
    4. Delete any stale ready-file so the probe's first write is not
       racing with a Tauri host already polling the old file (D-05).
    5. Spawn the health-probe thread BEFORE ``socketio.run`` — the call
       below blocks the main thread for the server's lifetime, so the
       probe has to be on a daemon sub-thread or the ready-file is never
       written (Pitfall #1; RESEARCH.md Pattern 4).
    6. Bind loopback (127.0.0.1) only — never 0.0.0.0 (Sec-7). Werkzeug
       debug mode is disabled because the auto-reloader's subprocess
       breaks both PyInstaller --onefile and the ready-file protocol.
       ``allow_unsafe_werkzeug=True`` is required by Flask-SocketIO 5+
       in production and is the correct choice for a single-user
       localhost desktop sidecar.
    """
    parser = argparse.ArgumentParser(
        prog="backend",
        description="LoL Draft Analyzer backend sidecar.",
    )
    parser.add_argument(
        '--port', type=int, default=5000,
        help='TCP port to bind 127.0.0.1 on (default: 5000 for native dev; 0 = OS-assigned).',
    )
    parser.add_argument(
        '--ready-file', type=Path, default=None,
        help='Path to write the JSON ready-marker after /api/health returns 200.',
    )
    parser.add_argument(
        '--cache-dir', type=Path, default=None,
        help='Override platformdirs.user_cache_dir().',
    )
    parser.add_argument(
        '--log-dir', type=Path, default=None,
        help='Override platformdirs.user_log_dir().',
    )
    args = parser.parse_args()

    # Resolve the log dir FIRST so every subsequent step is logged. D-01
    # allows CLI override; fall back to platformdirs.user_log_dir() which
    # auto-creates the directory (ensure_exists=True in the helper).
    log_dir = args.log_dir or user_log_dir()
    _configure_logging(log_dir)
    log = logging.getLogger(__name__)
    log.info("[BOOT] app=%s port=%d log_dir=%s", LOL_DRAFT_APP_NAME, args.port, log_dir)

    # cache_dir is exposed as a CLI flag for Phase 3 / tests. Phase 2 will
    # wire it into json_repo.py; Phase 1 only needs the directory to exist
    # so that the existing CACHE_FILE read path (now under user_cache_dir())
    # has a valid parent.
    cache_dir = args.cache_dir or user_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Make bundled certifi the source of truth for SSL (Pitfall #7 / D-10).
    # In frozen mode the spec drops cacert.pem into _MEIPASS/certifi/; in
    # dev mode the file does not exist at that path and requests falls
    # back to its pip-installed certifi (also correct).
    cacert = bundled_resource("certifi/cacert.pem")
    if cacert.exists():
        os.environ.setdefault("SSL_CERT_FILE", str(cacert))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(cacert))
        log.info("[BOOT] SSL_CERT_FILE=%s", cacert)

    # D-05: idempotent cleanup of stale ready-file. Must happen BEFORE
    # the probe thread starts so the probe's atomic write is not racing
    # with a host checking for the file.
    if args.ready_file is not None and args.ready_file.exists():
        args.ready_file.unlink()

    # Phase 2 CDN-08: warm the CDN cache before declaring ready. CDNError
    # aborts startup loudly (Tauri's probe will time out and Phase 3's UX
    # layer will replace this with a friendly error banner — first-run
    # offline UX is intentionally deferred per D-19 + N-05).
    try:
        _json_repo_warm_cache()
    except _json_repo_CDNError as exc:
        log.error("[json_repo] warm_cache failed: %s", exc)
        # Fail loud — do NOT write ready-file. Tauri will time out the probe
        # and show the Phase 3 AV-troubleshooting dialog (TAURI-07).
        os.write(2, f"[json_repo] warm_cache failed: {exc}\n".encode())
        os._exit(2)

    # D-02 / D-03 + Pattern 4: spawn probe BEFORE socketio.run.
    # daemon=True so it does not keep the process alive after the server
    # returns from socketio.run (SIGTERM / CTRL_BREAK_EVENT / Ctrl+C).
    probe = threading.Thread(
        target=_probe_health_then_signal_ready,
        args=(args.port, args.ready_file),
        name="health-probe",
        daemon=True,
    )
    probe.start()

    # Startup banner — logged at INFO so it appears in the log file
    # as well as on the console (StreamHandler added below in dev mode).
    log.info("=" * 60)
    log.info("COUNTERPICK DRAFT TRACKER BACKEND")
    log.info("=" * 60)
    log.info("Verfügbare Endpunkte:")
    log.info("  GET  /api/health                    - Health Check")
    log.info("  GET  /api/champions/list            - Champion-Liste")
    log.info("  GET  /api/primary-roles             - Primary Roles Mapping")
    log.info("  POST /api/recommendations           - Recommendation Engine")
    log.info("  GET  /api/league-client/status      - League Client Status")
    log.info("  GET  /api/league-client/draft       - League Client Draft-Daten")
    log.info("  GET  /api/league-client/session     - League Client Session-Daten")
    log.info("  POST /api/set-role                  - Manuelle Rollen-Überschreibung")
    log.info("=" * 60)
    log.info("Cache-Dauer: %ds (%d Minuten)", CACHE_DURATION, CACHE_DURATION // 60)
    log.info("Bind: 127.0.0.1:%d", args.port)
    log.info("=" * 60)

    # Security (Sec-7): bind loopback ONLY, never 0.0.0.0.
    # debug=False: Werkzeug reloader spawns a subprocess that breaks
    #   PyInstaller --onefile and the ready-file protocol (Pitfall #7 in
    #   RESEARCH.md; RESEARCH.md Anti-Patterns table).
    # allow_unsafe_werkzeug=True: Flask-SocketIO >=5 raises RuntimeError
    #   in production without it; correct for a single-user localhost
    #   desktop sidecar.
    socketio.run(
        app,
        host="127.0.0.1",
        port=args.port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()

