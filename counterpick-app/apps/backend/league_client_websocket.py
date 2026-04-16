"""
League Client WebSocket Wrapper
Stellt WebSocket-Verbindung zur League Client API her für Echtzeit-Draft-Events
"""
import websocket
import json
import logging
import threading
import time
import ssl
from typing import Optional, Callable, Dict
import urllib3
from league_client_auth import get_league_client_info, get_auth_header
import base64

logger = logging.getLogger(__name__)

# SSL-Warnungen unterdrücken
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# WebSocket-Verbindung
_ws_connection = None
_ws_thread = None
_event_callback = None
_reconnect_interval = 5  # Sekunden
_is_connected = False


def get_websocket_url() -> Optional[str]:
    """
    Holt WebSocket URL aus Prozess-Argumenten
    """
    client_info = get_league_client_info()
    if not client_info:
        return None
    
    port = client_info['port']
    protocol = 'wss' if client_info.get('protocol', 'https') == 'https' else 'ws'
    return f"{protocol}://127.0.0.1:{port}"


def get_websocket_headers() -> Dict[str, str]:
    """
    Holt WebSocket Auth-Header aus Prozess-Argumenten
    """
    client_info = get_league_client_info()
    if not client_info:
        return {}
    
    password = client_info['password']
    auth_header = get_auth_header(password)
    
    # WebSocket benötigt Authorization Header
    return {
        'Authorization': auth_header
    }


def on_message(ws, message):
    """
    Handler für WebSocket-Nachrichten
    """
    global _event_callback
    
    try:
        data = json.loads(message)
        
        # League Client API sendet Events als Array: [event_id, event_name, uri, data]
        if isinstance(data, list) and len(data) >= 3:
            event_id = data[0]
            event_name = data[1]
            # URI kann an Position 2 oder 3 sein, je nach Format
            if len(data) >= 4:
                uri = data[2] if isinstance(data[2], str) else data[2].get('uri', '') if isinstance(data[2], dict) else ''
                event_data = data[3] if len(data) > 3 else {}
            else:
                uri = ''
                event_data = data[2] if len(data) > 2 else {}
            
            # Nur Champion Select Events loggen und verarbeiten
            if event_name == 'OnJsonApiEvent':
                # Prüfe URI in event_data falls URI-String leer ist
                if isinstance(event_data, dict):
                    uri_from_data = event_data.get('uri', '')
                    if uri_from_data:
                        uri = uri_from_data
                
                # Nur relevante Events loggen (Champion Select, Gameflow Phase)
                relevant_uris = [
                    '/lol-champ-select/v1/session',
                    '/lol-gameflow/v1/gameflow-phase',
                    '/lol-champ-select/v1/current-champion'
                ]
                
                is_relevant = any(relevant_uri in uri for relevant_uri in relevant_uris)
                
                if is_relevant:
                    logger.info("Relevantes Event: %s", uri)
                
                # Prüfe ob es ein Champion Select Session Event ist
                if '/lol-champ-select/v1/session' in uri:
                    if _event_callback:
                        _event_callback({
                            'uri': uri,
                            'data': event_data if isinstance(event_data, dict) else {'data': event_data},
                            'eventType': event_name
                        })
                
                # Prüfe ob es ein Gameflow Phase Event ist (für Draft-Reset)
                elif '/lol-gameflow/v1/gameflow-phase' in uri:
                    if _event_callback:
                        _event_callback({
                            'uri': uri,
                            'data': event_data if isinstance(event_data, dict) else {'data': event_data},
                            'eventType': event_name
                        })
        # Fallback für Dictionary-Format
        elif isinstance(data, dict):
            uri = data.get('uri', '')
            # Nur relevante Events loggen
            relevant_uris = [
                '/lol-champ-select/v1/session',
                '/lol-gameflow/v1/gameflow-phase',
                '/lol-champ-select/v1/current-champion'
            ]
            
            if any(relevant_uri in uri for relevant_uri in relevant_uris):
                logger.info("Relevantes Event: %s", uri)
            
            if '/lol-champ-select/v1/session' in uri:
                if _event_callback:
                    _event_callback(data)
            elif '/lol-gameflow/v1/gameflow-phase' in uri:
                if _event_callback:
                    _event_callback(data)
    except json.JSONDecodeError as e:
        logger.debug("JSON Decode Error: %s, Message: %s", e, message[:100])
    except Exception as e:
        logger.debug("Fehler beim Verarbeiten der Nachricht: %s", e, exc_info=True)


def on_error(ws, error):
    """
    Handler für WebSocket-Fehler
    """
    global _is_connected
    _is_connected = False
    
    logger.debug("Fehler: %s", error)


def on_close(ws, close_status_code, close_msg):
    """
    Handler für WebSocket-Verbindungsabbruch
    """
    global _is_connected, _ws_connection
    _is_connected = False
    _ws_connection = None
    
    logger.debug("Verbindung geschlossen: %s - %s", close_status_code, close_msg)
    
    # Automatische Reconnection nur wenn:
    # 1. Callback gesetzt ist
    # 2. Kein Berechtigungsfehler (1008 = Policy Violation, 1002 = Protocol Error)
    # 3. Nicht manuell getrennt
    if _event_callback and close_status_code not in [1008, 1002]:
        # Prüfe ob League Client verfügbar ist (vermeidet Endlosschleife bei Berechtigungsfehlern)
        client_info = get_league_client_info()
        if client_info:
            time.sleep(_reconnect_interval)
            connect_to_league_client_websocket(_event_callback)
        else:
            logger.info("Keine Reconnection - League Client nicht verfügbar")


def on_open(ws):
    """
    Handler für WebSocket-Verbindungsaufbau
    """
    global _is_connected
    _is_connected = True
    
    logger.debug("Verbindung hergestellt")
    
    # Subscribe auf Champion Select Events
    subscribe_to_champion_select_events(ws)


def subscribe_to_champion_select_events(ws):
    """
    Subscribe auf Champion Select Session Events
    """
    try:
        # League Client API nutzt Event-Subscriptions
        # Format: [5, "OnJsonApiEvent", "/lol-champ-select/v1/session", {...}]
        subscribe_message = [5, "OnJsonApiEvent", "/lol-champ-select/v1/session", {}]
        ws.send(json.dumps(subscribe_message))
        
        logger.info("Subscribed auf Champion Select Events")
    except Exception as e:
        logger.debug("Fehler beim Subscribe: %s", e)


def connect_to_league_client_websocket(event_callback: Callable[[Dict], None]) -> bool:
    """
    Verbindet zum League Client WebSocket
    
    Args:
        event_callback: Callback-Funktion die bei Events aufgerufen wird
        
    Returns:
        True wenn Verbindung erfolgreich, False sonst
    """
    global _ws_connection, _ws_thread, _event_callback, _is_connected
    
    # Stoppe vorherige Verbindung
    disconnect_from_league_client_websocket()
    
    _event_callback = event_callback
    
    websocket_url = get_websocket_url()
    if not websocket_url:
        logger.warning("Keine WebSocket URL verfügbar (League Client nicht gefunden)")
        logger.warning("Stelle sicher, dass der League Client läuft und vollständig geladen ist!")
        return False
    
    headers = get_websocket_headers()
    
    try:
        # Erstelle WebSocket-Verbindung
        # WebSocket-Header müssen als Liste von Strings formatiert sein
        ws_headers = []
        if headers:
            for k, v in headers.items():
                ws_headers.append(f"{k}: {v}")
        
        logger.info("Verbinde zu %s", websocket_url)
        logger.debug("Headers: %s", ws_headers)
        
        ws = websocket.WebSocketApp(
            websocket_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
            header=ws_headers if ws_headers else None
        )
        
        _ws_connection = ws
        
        # Starte WebSocket in separatem Thread
        # SSL-Zertifikat-Verifikation deaktivieren (selbst-signiertes Zertifikat)
        _ws_thread = threading.Thread(
            target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
            daemon=True
        )
        _ws_thread.start()
        
        # Warte kurz auf Verbindung
        time.sleep(1)
        
        return _is_connected
        
    except Exception as e:
        logger.debug("Fehler beim Verbinden: %s", e)
        return False


def disconnect_from_league_client_websocket():
    """
    Trennt WebSocket-Verbindung
    """
    global _ws_connection, _ws_thread, _is_connected, _event_callback
    
    _event_callback = None
    
    if _ws_connection:
        try:
            _ws_connection.close()
        except:
            pass
        _ws_connection = None
    
    if _ws_thread and _ws_thread.is_alive():
        _ws_thread.join(timeout=1)
        _ws_thread = None
    
    _is_connected = False


def is_websocket_connected() -> bool:
    """
    Prüft ob WebSocket verbunden ist
    """
    return _is_connected and _ws_connection is not None

