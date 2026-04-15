"""
Live Client API Wrapper
Stellt Verbindung zur League of Legends Live Client API her
Nutzt requests für synchrone HTTP-Requests
"""
import requests
import json
from typing import Optional, Dict, List
import urllib3

# SSL-Warnungen unterdrücken (selbst-signiertes Zertifikat)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIVE_CLIENT_BASE_URL = "https://127.0.0.1:2999"
LIVE_CLIENT_TIMEOUT = 2  # 2 Sekunden Timeout


def is_client_running() -> bool:
    """
    Prüft ob der League Client läuft und erreichbar ist
    """
    try:
        response = requests.get(
            f"{LIVE_CLIENT_BASE_URL}/liveclientdata/gamestats",
            verify=False,
            timeout=LIVE_CLIENT_TIMEOUT
        )
        return response.status_code == 200
    except (requests.exceptions.RequestException, requests.exceptions.Timeout):
        return False


def get_game_stats() -> Optional[Dict]:
    """
    Holt grundlegende Game-Statistiken
    """
    try:
        response = requests.get(
            f"{LIVE_CLIENT_BASE_URL}/liveclientdata/gamestats",
            verify=False,
            timeout=LIVE_CLIENT_TIMEOUT
        )
        if response.status_code == 200:
            return response.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        # Client nicht erreichbar - normal wenn Client nicht läuft
        pass
    except Exception as e:
        if __debug__:
            print(f"[LIVE CLIENT] Fehler beim Abrufen der Game-Stats: {e}")
    return None


def get_all_players() -> List[Dict]:
    """
    Holt alle Spieler-Daten (inkl. Champion-Picks)
    """
    try:
        response = requests.get(
            f"{LIVE_CLIENT_BASE_URL}/liveclientdata/playerlist",
            verify=False,
            timeout=LIVE_CLIENT_TIMEOUT
        )
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.ConnectionError:
        # Client nicht erreichbar - normal wenn Client nicht läuft
        pass
    except requests.exceptions.Timeout:
        # Timeout - Client antwortet nicht
        pass
    except Exception as e:
        # Andere Fehler nur im Debug-Modus loggen
        if __debug__:
            print(f"[LIVE CLIENT] Fehler beim Abrufen der Spieler-Daten: {e}")
    return []


def get_events() -> List[Dict]:
    """
    Holt alle Game-Events (inkl. Draft-Events)
    """
    try:
        response = requests.get(
            f"{LIVE_CLIENT_BASE_URL}/liveclientdata/eventdata",
            verify=False,
            timeout=LIVE_CLIENT_TIMEOUT
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('Events', [])
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        # Client nicht erreichbar - normal wenn Client nicht läuft
        pass
    except Exception as e:
        if __debug__:
            print(f"[LIVE CLIENT] Fehler beim Abrufen der Events: {e}")
    return []


def get_draft_data() -> Optional[Dict]:
    """
    Analysiert Events und Spieler-Daten um Draft-Informationen zu extrahieren
    Gibt zurück: {team1_picks: [], team2_picks: [], bans: [], game_phase: string}
    """
    players = get_all_players()
    
    if not players:
        return None
    
    # Extrahiere Picks aus Spieler-Daten
    team1_picks = []
    team2_picks = []
    bans = []
    
    for player in players:
        champion = player.get('championName', '')
        team = player.get('team', '')
        
        if champion:
            pick_data = {
                'champion': champion,
                'summonerName': player.get('summonerName', ''),
                'riotId': player.get('riotId', ''),
                'riotIdGameName': player.get('riotIdGameName', ''),
                'riotIdTagLine': player.get('riotIdTagLine', '')
            }
            
            if team == 'ORDER':
                team1_picks.append(pick_data)
            elif team == 'CHAOS':
                team2_picks.append(pick_data)
    
    # Extrahiere Bans aus Events
    events = get_events()
    for event in events:
        event_name = event.get('EventName', '')
        # Bans werden in Events gespeichert, aber die genaue Struktur variiert
        # Für jetzt sammeln wir alle relevanten Events
        if 'Ban' in event_name or 'ChampionSelect' in event_name:
            # TODO: Bans aus Events extrahieren wenn Struktur bekannt
            pass
    
    # Bestimme Game-Phase
    game_phase = 'in_game' if len(team1_picks) == 5 and len(team2_picks) == 5 else 'draft'
    
    return {
        'team1_picks': team1_picks,
        'team2_picks': team2_picks,
        'bans': bans,
        'game_phase': game_phase
    }

