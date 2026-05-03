# Troubleshooting

## Problem: Lockfile wird nicht gefunden

### Lösung 1: League Client als Admin gestartet?
- Wenn Riot's Anti-Cheat den Client als erhöhten Prozess laufen lässt,
  liest das Backend (auf normaler User-Ebene) die Lockfile nicht.
- Workaround: League Client einmal ohne Admin starten, dann das Backend
  via `pnpm tauri dev` aus demselben User-Kontext.

### Lösung 2: Windows Firewall prüfen
- Windows Defender Firewall könnte lokale Verbindungen auf 127.0.0.1
  blockieren. Python.exe zur Ausnahmeliste hinzufügen:
  1. Windows Defender Firewall öffnen
  2. "Eine App durch die Firewall zulassen"
  3. Python.exe hinzufügen (private und öffentliche Netzwerke)

### Lösung 3: Antivirus-Software
- Manche Antivirus-Programme blockieren den Zugriff auf die Lockfile
- Füge den League of Legends Ordner zur Ausnahmeliste hinzu:
  `C:\Users\<Benutzername>\AppData\Local\Riot Games\League of Legends`

### Lösung 4: Lockfile manuell prüfen
- Führe `python check_lockfile.py` aus
- Sollte zeigen: `Existiert: True`
- Falls `False`: League Client ist nicht vollständig geladen

## Problem: "Connection refused" oder "Connection timeout"

### Lösung 1: League Client Status prüfen
- Stelle sicher, dass der League Client läuft
- Warte bis der Client vollständig geladen ist (Login-Screen sichtbar)
- Die Lockfile wird erst erstellt, wenn der Client vollständig geladen ist

### Lösung 2: Port-Zugriff prüfen
- Die League Client API nutzt einen dynamischen Port (aus Lockfile)
- Prüfe ob der Port erreichbar ist:
  ```python
  python test_league_client.py
  ```

## Problem: "Permission denied" oder "Access denied"

### Lösung 1: Berechtigungen prüfen
- Prüfe ob der Benutzer Leseberechtigung für den League of Legends Ordner hat:
  `C:\Users\<Benutzername>\AppData\Local\Riot Games\League of Legends`
- Rechtsklick auf Ordner → Eigenschaften → Sicherheit → Prüfe Berechtigungen

## Problem: "401 Unauthorized" oder "403 Forbidden"

### Lösung 1: Lockfile neu lesen
- Die Lockfile wird bei jedem Client-Start neu erstellt
- Stoppe die App und starte sie neu (Tauri-Fenster schließen, dann
  wieder `pnpm tauri dev` oder die installierte App öffnen)
- Stelle sicher, dass der League Client läuft

## Problem: WebSocket-Verbindung schlägt fehl

### Lösung 1: SSL-Zertifikat
- Der League Client nutzt selbst-signierte SSL-Zertifikate
- Das ist normal und wird automatisch behandelt
- Falls Probleme auftreten, prüfe ob `ssl` Modul importiert ist

### Lösung 2: HTTP-Polling Fallback
- Falls WebSocket nicht funktioniert, nutzt das System automatisch HTTP-Polling
- Status sollte "HTTP-Polling aktiv" anzeigen
- Das ist langsamer, aber funktioniert auch ohne WebSocket

## Problem: Draft-Daten werden nicht angezeigt

### Lösung 1: Champion Select prüfen
- Stelle sicher, dass du in Champion Select bist
- Die API funktioniert nur während der Draft-Phase
- Nicht im Practice Tool oder während des Spiels

### Lösung 2: Frontend prüfen
- Öffne Browser-Console (F12)
- Prüfe auf Fehler in der Console
- Prüfe ob WebSocket-Verbindung besteht

### Lösung 3: Backend-Logs prüfen
- Prüfe die Backend-Ausgabe auf Fehlermeldungen
- Suche nach `[LOCKFILE]`, `[WEBSOCKET]`, `[LEAGUE CLIENT]` Meldungen

## Allgemeine Tipps

1. **League Client zuerst starten**: Warte bis der Client vollständig geladen ist
2. **App neu starten**: Tauri-Fenster schließen → erneut öffnen, damit der
   Sidecar mit frischen Pfaden hochfährt
3. **Logs prüfen**:
   - Dev-Modus: `%APPDATA%\dev.till.lol-draft-analyzer\logs\backend.log`
   - Installierte App: `%LOCALAPPDATA%\lol-draft-analyzer\lol-draft-analyzer\Logs\backend.log`

## Bekannte Einschränkungen

- **Practice Tool**: Die League Client API funktioniert nicht im Practice Tool
- **Live Game**: Während des Spiels sind keine Draft-Daten verfügbar
- **Client-Neustart**: Nach Client-Neustart muss Backend neu gestartet werden

## Weitere Hilfe

- Prüfe die Backend-Logs für detaillierte Fehlermeldungen
- Prüfe die Browser-Console (F12) für Frontend-Fehler
- Stelle sicher, dass alle Dependencies installiert sind: `pip install -r requirements.txt`

