"""
League Client API Authentication Helper
Liest Prozess-Argumente des LeagueClientUx.exe Prozesses für Authentifizierung
Implementiert nach Draftgap-Methode
"""
import os
import base64
import logging
import subprocess
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def get_league_client_info_from_process() -> Optional[Dict]:
    """
    Holt League Client Info aus Prozess-Argumenten (wie Draftgap)
    Liest Port und Auth-Token direkt aus den CommandLine-Argumenten des LeagueClientUx.exe Prozesses
    
    Gibt zurück: {port: int, password: str, username: str, protocol: str}
    """
    try:
        # PowerShell-Befehl um CommandLine des LeagueClientUx.exe Prozesses zu bekommen
        ps_command = (
            "Get-CimInstance -Query "
            "\"SELECT * from Win32_Process WHERE name LIKE 'LeagueClientUx.exe'\" "
            "| Select-Object -ExpandProperty CommandLine"
        )
        
        # Führe PowerShell-Befehl aus (versuche zuerst normal, dann mit vollem Pfad)
        try:
            result = subprocess.run(
                ["powershell", "/C", ps_command],
                capture_output=True,
                text=True,
                creationflags=0x08000000  # CREATE_NO_WINDOW (Windows)
            )
        except Exception:
            # Fallback: Versuche mit vollem PowerShell-Pfad
            result = subprocess.run(
                ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell", "/C", ps_command],
                capture_output=True,
                text=True,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
        
        if result.returncode != 0 or not result.stdout:
            logger.warning("LeagueClientUx.exe Prozess nicht gefunden")
            logger.debug("PowerShell Output: %s", result.stdout)
            logger.debug("PowerShell Error: %s", result.stderr)
            return None
        
        command_line = result.stdout.strip()
        
        if not command_line:
            logger.warning("CommandLine ist leer - League Client läuft möglicherweise nicht")
            return None
        
        # Extrahiere Port mit Regex
        port_match = re.search(r'--app-port=(\d+)', command_line)
        if not port_match:
            logger.warning("Port nicht in Prozess-Argumenten gefunden")
            logger.debug("CommandLine: %s...", command_line[:200])
            return None
        
        port = int(port_match.group(1))
        
        # Extrahiere Auth-Token mit Regex
        password_match = re.search(r'--remoting-auth-token=([a-zA-Z0-9_-]+)', command_line)
        if not password_match:
            logger.warning("Auth-Token nicht in Prozess-Argumenten gefunden")
            return None
        
        password = password_match.group(1)
        
        logger.info("League Client gefunden! Port: %d, Token: %d Zeichen", port, len(password))
        
        return {
            'port': port,
            'password': password,
            'username': 'riot',
            'protocol': 'https'
        }
        
    except FileNotFoundError:
        logger.error("PowerShell nicht gefunden - ist Windows installiert?")
        return None
    except Exception as e:
        logger.error("Fehler beim Auslesen der Prozess-Argumente: %s", e, exc_info=True)
        return None


def get_auth_header(password: str) -> str:
    """
    Erstellt Basic Auth Header aus Password
    """
    # Base64 encode "riot:{password}"
    credentials = f"riot:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def get_league_client_info() -> Optional[Dict]:
    """
    Holt League Client Info aus Prozess-Argumenten
    Gibt zurück: {port: int, password: str, auth_header: str, protocol: str}
    """
    client_info = get_league_client_info_from_process()
    
    if not client_info:
        logger.warning("League Client Info nicht verfügbar")
        logger.warning("Stelle sicher, dass der League Client läuft und vollständig geladen ist!")
        return None
    
    return {
        'port': client_info['port'],
        'password': client_info['password'],
        'auth_header': get_auth_header(client_info['password']),
        'protocol': client_info['protocol'],
        'username': client_info['username']
    }
