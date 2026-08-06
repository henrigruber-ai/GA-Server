# Test- und Stage-Prüfung 0.3.0

## Automatisiert

```powershell
ruff check .
ruff format --check .
mypy app
pytest -m "not e2e" --cov=app --cov-report=term-missing
pytest -m e2e
alembic upgrade head
alembic upgrade head
docker build -t ga-server:local .
.\scripts\check-secrets.ps1
```

Die Browserregression startet mit einem echten historischen Minutenpunkt,
verkürzt den 10-Sekunden-Takt auf 80 Millisekunden, liefert danach mehrfach
leere Antworten und prüft, dass Kurve und Zoom sichtbar bleiben. Außerdem wird
die Anzahl der Requests und öffentlichen WebSocket-Verbindungen kontrolliert.

## Manuelle Stage-Prüfung

1. Desktop und 360-px-Ansicht ohne horizontalen Überlauf öffnen.
2. Prüfen, dass die Legende initial geschlossen ist.
3. GA per Tab fokussieren und mit Enter sowie Leertaste bedienen.
4. Reihen einzeln wählen, Zoom setzen und mindestens drei Refreshes abwarten.
5. Leere/fehlerhafte Historienantwort simulieren; letzte gültige Kurve muss
   erhalten bleiben.
6. Als Benutzer anmelden und „Steckdosen-Übersicht“ im Burger-Menü öffnen.
7. Messkachel ohne Schalter und steuerbare Kachel mit Schalter prüfen.
8. Online, Offline, Pending, Bestätigung, Konflikt und Timeout prüfen.
9. Sicherstellen, dass Ein/Aus erst nach POWER-Bestätigung wechselt.
10. Seite neu laden; bestätigter Zustand muss aus dem Snapshot erscheinen.
11. Browserkonsole auf Fehler und Network-Ansicht auf doppelte Timer/WebSockets
    prüfen.
12. Shelly Pro 3EM, Minutenaggregation, Cleanup und Healthchecks erneut prüfen.

Screenshots für den Pull Request dürfen keine Cookies, Tokens, Benutzernamen,
MQTT-Zugangsdaten oder andere Secrets zeigen.
