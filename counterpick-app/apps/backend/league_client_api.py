"""
League Client API Wrapper
Stellt Verbindung zur League of Legends Client API her (für Draft-Phase)
Nutzt requests für synchrone HTTP-Requests
Implementiert nach Draftgap-Methode (Prozess-Argumente)
"""
import logging
import requests
import json
from typing import Optional, Dict, List
import urllib3
import os
from pathlib import Path
from league_client_auth import get_league_client_info

logger = logging.getLogger(__name__)

# SSL-Warnungen unterdrücken (selbst-signiertes Zertifikat)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Champion-ID zu Name Mapping (wird beim ersten Aufruf geladen)
_champion_id_map = None

LEAGUE_CLIENT_TIMEOUT = 2  # 2 Sekunden Timeout

# Cache für Client-Info (wie Draftgap)
_client_info_cache = None


def _get_lcu_response(path: str) -> Optional[Dict]:
    """
    Holt LCU API Response (wie Draftgap)
    Cached Client-Info und invalidiert bei Fehlern
    """
    global _client_info_cache
    
    # Hole Client-Info wenn nicht gecached
    if _client_info_cache is None:
        client_info = get_league_client_info()
        if not client_info:
            return None
        _client_info_cache = client_info
    
    port = _client_info_cache['port']
    password = _client_info_cache['password']
    username = _client_info_cache.get('username', 'riot')
    protocol = _client_info_cache.get('protocol', 'https')
    
    url = f"{protocol}://127.0.0.1:{port}/{path}"
    
    try:
        response = requests.get(
            url,
            verify=False,  # Nutze verify=False (Riot-Zertifikat wird trotzdem akzeptiert)
            timeout=LEAGUE_CLIENT_TIMEOUT,
            auth=(username, password)  # Basic Auth direkt mit requests
        )
        
        if response.status_code == 404:
            return None
        
        if response.status_code == 401:
            # Auth-Fehler - invalidiere Cache
            _client_info_cache = None
            logger.warning("Authentifizierungsfehler (401) - Cache invalidiert")
            return None
        
        if response.status_code == 200:
            return response.json()
        
        return None
        
    except requests.exceptions.ConnectionError:
        # Connection Error - invalidiere Cache (Client möglicherweise neu gestartet)
        _client_info_cache = None
        return None
    except Exception as e:
        # Bei anderen Fehlern Cache invalidieren
        _client_info_cache = None
        logger.debug("Fehler bei Request: %s", e)
        return None


def get_client_base_url() -> str:
    """
    Holt die Base URL aus Prozess-Argumenten
    """
    global _client_info_cache
    
    if _client_info_cache is None:
        client_info = get_league_client_info()
        if client_info:
            _client_info_cache = client_info
        else:
            return ""  # Kein Client gefunden
    
    port = _client_info_cache['port']
    protocol = _client_info_cache.get('protocol', 'https')
    return f"{protocol}://127.0.0.1:{port}"


def get_auth_headers() -> Dict[str, str]:
    """
    Holt Auth-Header aus Prozess-Argumenten
    Gibt leeres Dict zurück wenn Client-Info nicht verfügbar
    """
    global _client_info_cache
    
    if _client_info_cache is None:
        client_info = get_league_client_info()
        if client_info:
            _client_info_cache = client_info
        else:
            return {}
    
    if _client_info_cache and 'auth_header' in _client_info_cache:
        return {
            'Authorization': _client_info_cache['auth_header']
        }
    return {}


def _load_champion_id_map() -> Dict[int, str]:
    """
    Lädt Champion-ID zu Name Mapping.
    Primäre Quelle: json_repo (CDN-backed, funktioniert auch im PyInstaller-Bundle)
    Fallback: Data Dragon (lokal, nur im Dev-Setup verfügbar)
    """
    global _champion_id_map

    # Cache only once populated. A prior call during json_repo warm_cache
    # could return {} before the champions table is resolved; caching
    # that empty dict would permanently poison the lookup.
    if _champion_id_map:
        return _champion_id_map

    _champion_id_map = {}

    # 1. json_repo (CDN) — einzige Quelle die im gepackten Client verfügbar ist
    try:
        from lolalytics_api.json_repo import _champion_map
        maps = _champion_map()
        key_to_name = maps.get("key_to_name", {})

        for key_str, name in key_to_name.items():
            try:
                champ_id = int(key_str)
                if champ_id > 0 and name:
                    _champion_id_map[champ_id] = name
            except (ValueError, TypeError):
                continue

        if _champion_id_map:
            logger.info("Champion-Mapping aus json_repo geladen: %d Champions", len(_champion_id_map))
            return _champion_id_map
    except Exception as e:
        logger.info("json_repo-Mapping fehlgeschlagen, nutze Dragontail-Fallback: %s", e)
    
    # 2. Fallback: Data Dragon lokal (dragontail-15.24.1)
    base_path = Path(__file__).parent.parent
    dragontail_path = base_path / "dragontail-15.24.1"
    
    if dragontail_path.exists():
        # Suche nach neuestem Patch-Ordner
        patch_dirs = [d for d in dragontail_path.iterdir() if d.is_dir() and d.name.replace('.', '').isdigit()]
        if patch_dirs:
            latest_patch = sorted(patch_dirs, key=lambda x: x.name, reverse=True)[0]
            data_path = latest_patch / "data" / "en_US" / "champion"
            
            if data_path.exists():
                for champ_file in data_path.glob("*.json"):
                    try:
                        with open(champ_file, 'r', encoding='utf-8') as f:
                            champ_data = json.load(f)
                            champ_info = champ_data.get('data', {})
                            for champ_key, champ_details in champ_info.items():
                                champ_id = int(champ_details.get('key', 0))
                                champ_name = champ_details.get('name', '')
                                if champ_id > 0 and champ_name:
                                    _champion_id_map[champ_id] = champ_name
                    except Exception as e:
                        logger.debug("Fehler beim Laden von %s: %s", champ_file, e)
        
        if _champion_id_map:
            logger.info("Champion-Mapping aus Dragontail geladen: %d Champions", len(_champion_id_map))
    
    return _champion_id_map


def get_champion_name_by_id(champion_id: int) -> str:
    """
    Konvertiert Champion-ID zu Name
    """
    champion_map = _load_champion_id_map()
    return champion_map.get(champion_id, f"Champion {champion_id}")


def is_league_client_running() -> bool:
    """
    Prüft ob der League Client läuft und erreichbar ist.

    Nutzt /lol-gameflow/v1/gameflow-phase statt /session — phase gibt immer
    200 zurück solange der Client erreichbar ist (mit "None", "Lobby",
    "ChampSelect", "InProgress" etc.), während /session 404 gibt wenn keine
    Game-Session läuft (z.B. in der Lobby). Ein 404 ist also KEIN Signal
    dass der Client offline ist — es heißt nur dass aktuell kein Spiel
    aktiv ist. Connection-/Timeout-Fehler sind die echten "nicht running"
    Signale.
    """
    try:
        base_url = get_client_base_url()
        headers = get_auth_headers()
        response = requests.get(
            f"{base_url}/lol-gameflow/v1/gameflow-phase",
            verify=False,
            timeout=LEAGUE_CLIENT_TIMEOUT,
            headers=headers
        )
        # 2xx = Client läuft und antwortet (auch wenn keine Session aktiv).
        # 4xx ohne Auth hiesse Token falsch — immer noch "Client läuft".
        # Nur ConnectionError/Timeout = Client nicht erreichbar.
        return response.status_code < 500
    except (requests.exceptions.RequestException, requests.exceptions.Timeout):
        return False


def get_draft_session() -> Optional[Dict]:
    """
    Holt Draft-Session-Daten (Champion Select)
    Nutzt Prozess-Argumente-Methode (wie Draftgap)
    """
    return _get_lcu_response("lol-champ-select/v1/session")


def get_gameflow_session() -> Optional[Dict]:
    """
    Holt Gameflow-Session-Daten (aktueller Spiel-Status)
    Nutzt Prozess-Argumente-Methode (wie Draftgap)
    """
    return _get_lcu_response("lol-gameflow/v1/session")


def normalize_assigned_position(position: str) -> str:
    """
    Normalisiert LCU assignedPosition zu Standard-Rollen.
    
    Args:
        position: LCU Position (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
        
    Returns:
        str: Normalisierte Rolle ('top', 'jungle', 'middle', 'bottom', 'support')
    """
    if not position:
        return ''
    
    role_map = {
        'TOP': 'top',
        'JUNGLE': 'jungle',
        'MIDDLE': 'middle',
        'BOTTOM': 'bottom',
        'UTILITY': 'support',
        # Lowercase-Varianten
        'top': 'top',
        'jungle': 'jungle',
        'middle': 'middle',
        'mid': 'middle',
        'bottom': 'bottom',
        'utility': 'support',
        'support': 'support'
    }
    
    return role_map.get(position, role_map.get(position.upper(), ''))


def get_draft_picks_bans() -> Optional[Dict]:
    """
    Extrahiert Picks und Bans aus Draft-Session
    Gibt zurück: {team1_picks: [], team2_picks: [], team1_bans: [], team2_bans: [], phase: string}
    """
    session = get_draft_session()
    
    if not session:
        return None
    
    team1_picks = []
    team2_picks = []
    team1_bans = []
    team2_bans = []
    
    # Extrahiere Phase
    phase = session.get('timer', {}).get('phase', 'UNKNOWN')
    
    # Extrahiere Teams
    my_team = session.get('myTeam', [])
    their_team = session.get('theirTeam', [])
    
    # Lade Champion-ID Mapping
    champion_map = _load_champion_id_map()
    
    # WICHTIG: Bestimme myTeam basierend auf localPlayerCellId VOR der Zuordnung
    # cellIds 0-4 = Blue Side (team1), cellIds 5-9 = Red Side (team2)
    local_cell_id = session.get('localPlayerCellId')
    if local_cell_id is not None:
        is_blue_side = local_cell_id < 5
        my_team_number = 0 if is_blue_side else 1
        logger.info("localPlayerCellId=%s -> is_blue_side=%s, myTeam=%s", local_cell_id, is_blue_side, my_team_number)
    else:
        # Fallback: myTeam ist team1
        is_blue_side = True
        my_team_number = 0
        logger.info("Kein localPlayerCellId -> Fallback zu Blue Side")
    
    # Extrahiere Picks und Hovers für ALLE Spieler (auch ohne Pick/Hover)
    # championId = gepickter Champion (locked)
    # championPickIntent = gehoverter Champion (noch nicht gepickt)
    # Beide können gleichzeitig existieren (z.B. wenn man einen anderen Champion hovert während man bereits einen gepickt hat)
    for member in my_team:
        champion_id = member.get('championId', 0)
        champion_pick_intent = member.get('championPickIntent', 0)
        
        # Erfasse Pick (wenn vorhanden)
        if champion_id > 0:
            pick_champion_name = champion_map.get(champion_id, f"Champion {champion_id}")
        else:
            pick_champion_name = ''
        
        # Erfasse Hover (wenn vorhanden)
        hover_champion_name = ''
        if champion_pick_intent > 0:
            hover_champion_name = champion_map.get(champion_pick_intent, f"Champion {champion_pick_intent}")
        
        # Wenn kein Pick aber Hover vorhanden, setze champion auf Hover (für Frontend-Kompatibilität)
        display_champion_name = pick_champion_name if pick_champion_name else hover_champion_name
        
        # Extrahiere und normalisiere Rolle
        assigned_position = member.get('assignedPosition', '')
        normalized_role = normalize_assigned_position(assigned_position)
        
        # Erstelle Pick-Daten
        pick_data = {
            'championId': champion_id,
            'champion': display_champion_name,  # Zeige Hover wenn kein Pick vorhanden
            'summonerId': member.get('summonerId', ''),
            'cellId': member.get('cellId', 0),
            'isLocked': champion_id > 0,
            'hoverChampionId': champion_pick_intent if champion_pick_intent > 0 and champion_pick_intent != champion_id else 0,
            'hoverChampion': hover_champion_name if champion_pick_intent > 0 and champion_pick_intent != champion_id else '',
            'assignedPosition': assigned_position,  # LCU Position (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
            'role': normalized_role  # Normalisierte Rolle für Frontend
        }
        
        # WICHTIG: Zuordnung basierend auf Side
        if is_blue_side:
            team1_picks.append(pick_data)  # Blue Side: myTeam → team1_picks
        else:
            team2_picks.append(pick_data)  # Red Side: myTeam → team2_picks
    
    for member in their_team:
        champion_id = member.get('championId', 0)
        champion_pick_intent = member.get('championPickIntent', 0)
        
        # Erfasse Pick (wenn vorhanden)
        if champion_id > 0:
            pick_champion_name = champion_map.get(champion_id, f"Champion {champion_id}")
        else:
            pick_champion_name = ''
        
        # Erfasse Hover (wenn vorhanden)
        hover_champion_name = ''
        if champion_pick_intent > 0:
            hover_champion_name = champion_map.get(champion_pick_intent, f"Champion {champion_pick_intent}")
        
        # Wenn kein Pick aber Hover vorhanden, setze champion auf Hover (für Frontend-Kompatibilität)
        display_champion_name = pick_champion_name if pick_champion_name else hover_champion_name
        
        # Extrahiere und normalisiere Rolle (auch für gegnerisches Team)
        assigned_position = member.get('assignedPosition', '')
        normalized_role = normalize_assigned_position(assigned_position)
        
        # Erstelle Pick-Daten
        pick_data = {
            'championId': champion_id,
            'champion': display_champion_name,  # Zeige Hover wenn kein Pick vorhanden
            'summonerId': member.get('summonerId', ''),
            'cellId': member.get('cellId', 0),
            'isLocked': champion_id > 0,
            'hoverChampionId': champion_pick_intent if champion_pick_intent > 0 and champion_pick_intent != champion_id else 0,
            'hoverChampion': hover_champion_name if champion_pick_intent > 0 and champion_pick_intent != champion_id else '',
            'assignedPosition': assigned_position,  # LCU Position (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
            'role': normalized_role  # Normalisierte Rolle für Frontend
        }
        
        # WICHTIG: Zuordnung basierend auf Side (UMGEKEHRT für theirTeam)
        if is_blue_side:
            team2_picks.append(pick_data)  # Blue Side: theirTeam → team2_picks
        else:
            team1_picks.append(pick_data)  # Red Side: theirTeam → team1_picks
    
    # Extrahiere Bans direkt aus session.bans (wie Draftgap)
    # Das ist zuverlässiger als aus Actions zu extrahieren
    bans_data = session.get('bans', {})
    if isinstance(bans_data, dict):
        # myTeamBans = Eigene Bans
        my_team_bans_list = bans_data.get('myTeamBans', [])
        if isinstance(my_team_bans_list, list):
            for champion_id in my_team_bans_list:
                if champion_id and champion_id > 0:
                    champion_name = champion_map.get(champion_id, f"Champion {champion_id}")
                    ban_data = {
                        'championId': champion_id,
                        'champion': champion_name,
                        'completed': True  # myTeamBans enthält nur completed Bans
                    }
                    # WICHTIG: Zuordnung basierend auf Side
                    target_bans = team1_bans if is_blue_side else team2_bans
                    # Prüfe ob dieser Ban bereits existiert (vermeide Duplikate)
                    if not any(b.get('championId') == champion_id for b in target_bans):
                        target_bans.append(ban_data)
        
        # theirTeamBans = Gegner-Bans
        their_team_bans_list = bans_data.get('theirTeamBans', [])
        if isinstance(their_team_bans_list, list):
            for champion_id in their_team_bans_list:
                if champion_id and champion_id > 0:
                    champion_name = champion_map.get(champion_id, f"Champion {champion_id}")
                    ban_data = {
                        'championId': champion_id,
                        'champion': champion_name,
                        'completed': True  # theirTeamBans enthält nur completed Bans
                    }
                    # WICHTIG: Zuordnung basierend auf Side (UMGEKEHRT für theirTeam)
                    target_bans = team2_bans if is_blue_side else team1_bans
                    # Prüfe ob dieser Ban bereits existiert (vermeide Duplikate)
                    if not any(b.get('championId') == champion_id for b in target_bans):
                        target_bans.append(ban_data)
    
    # Fallback: Falls session.bans nicht verfügbar ist, nutze Actions (für unvollständige Bans)
    if not team1_bans and not team2_bans:
        actions = session.get('actions', [])
        if isinstance(actions, list):
            for action_set in actions:
                if isinstance(action_set, list):
                    for action in action_set:
                        action_type = action.get('type', '')
                        if action_type == 'ban':
                            champion_id = action.get('championId', 0)
                            team_id = action.get('teamId', 0)
                            completed = action.get('completed', False)
                            
                            if champion_id > 0:
                                champion_name = champion_map.get(champion_id, f"Champion {champion_id}")
                                ban_data = {
                                    'championId': champion_id,
                                    'champion': champion_name,
                                    'completed': completed
                                }
                                if team_id == 100:  # Team 1 (Blue Side)
                                    if not any(b.get('championId') == champion_id for b in team1_bans):
                                        team1_bans.append(ban_data)
                                elif team_id == 200:  # Team 2 (Red Side)
                                    if not any(b.get('championId') == champion_id for b in team2_bans):
                                        team2_bans.append(ban_data)
    
    # my_team_number wurde bereits oben bestimmt basierend auf localPlayerCellId
    
    return {
        'team1_picks': team1_picks,
        'team2_picks': team2_picks,
        'team1_bans': team1_bans,
        'team2_bans': team2_bans,
        'phase': phase,
        'session': session,
        'myTeam': my_team_number  # 0 = team1 (Blue Side), 1 = team2 (Red Side)
    }

