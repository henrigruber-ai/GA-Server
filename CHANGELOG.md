<!--
File: CHANGELOG.md
Version: 0.3.2
Date: 2026-08-07
Purpose: Records user-visible changes by semantic version.
-->

# Versionshistorie

## 0.3.2 – 2026-08-07

- Tasmota-Steckdosen können mit ihrem nackten Tasmota-Gerätetopic, zum Beispiel `id139`, angelegt werden.
- Beim Wechsel eines bestehenden Geräts auf Tasmota führt ein ungültiges Topic nicht mehr zu HTTP 500, sondern zu einer verständlichen Validierungsmeldung.
- Regressionstests decken das Anlegen einer Tasmota-Steckdose sowie die Bearbeitung mit gültigem und ungültigem Gerätetopic ab.

## 0.3.1 – 2026-08-07

- MQTT-Passwörter können für Geräte wieder über die Administration gesetzt und geändert werden.
- Gerätepasswörter werden ausschließlich als Argon2-Hash gespeichert und weder über die API noch in der Oberfläche zurückgegeben.
- Beim Bearbeiten bleibt ein bereits gesetztes MQTT-Passwort erhalten, wenn das Passwortfeld leer gelassen wird; ein neu eingegebenes Passwort ersetzt den bisherigen Hash.
- MQTT-Passwörter werden nicht in Audit-Details übernommen. Regressionstests sichern Anlegen, unverändertes Bearbeiten und Passwortwechsel ab.

## 0.3.0 – 2026-08-06

- Tasmota-Steckdosen werden über strikt klassifizierte MQTT-Topics erfasst;
  SENSOR und STATUS10 fließen in denselben LiveStore und Minutenaggregator wie
  Shelly Pro 3EM.
- Eine geschützte, responsive „Steckdosen-Übersicht“ zeigt Roh-Livewerte,
  Onlinezustand, bestätigten Relaiszustand und nur bei ausdrücklich steuerbaren
  Geräten einen Schalter.
- Schaltbefehle werden serverseitig ausschließlich als `ON` oder `OFF` mit
  QoS 1 und ohne Retain veröffentlicht. Die Oberfläche übernimmt einen
  Endzustand erst nach passender Tasmota-POWER-Bestätigung.
- Thread-sicherer ControlStateStore, fünf Sekunden Timeout, Konflikterkennung,
  Reconnect-Abfrage, getrennte geschützte Control-WebSockets und Auditereignisse
  ergänzt.
- Geräte um `device_type`, `controllable` und `relay_index` erweitert; additive,
  idempotente Alembic-Migration für bestehende SQLite-Datenbanken ergänzt.
- „GA“ ist jetzt der einzige barrierefreie Legenden-Schalter; die Legende ist
  nach jedem Seitenaufruf zunächst geschlossen.
- Historienaktualisierungen behalten die letzte gültige Darstellung bei, wenn
  eine Folgeantwort leer oder fehlerhaft ist. Auswahl und Zoom bleiben erhalten.
- Regressionstests für wiederholte Aktualisierungen, Parser, Steuerablauf,
  API-Sicherheit, Migration, responsive Darstellung und bestehende Shelly-Flows
  ergänzt.

## 0.2.0 – 2026-08-04

- Strommonitor: Die Auswahl von Messstellen, Strom, Spannung, Leistung und
  Phasen wurde in eine ausklappbare Diagrammlegende integriert.
- Strommonitor: Beliebige Messgrößen und Phasen mehrerer Messstellen können
  jetzt gleichzeitig dargestellt werden.
- Strommonitor: Jede Datenreihe besitzt eine eindeutige und konsistente Farbe
  sowie ein zur Phase passendes Linienmuster.
- Strommonitor: Livewerte werden direkt in der Legende angezeigt und
  sekündlich aus den zuletzt empfangenen Rohwerten aktualisiert.
- Strommonitor: Das Diagramm wird unabhängig davon alle zehn Sekunden
  gebündelt aus den historischen Minutenwerten aktualisiert.
- Strommonitor: Die bisherigen Livewert-Karten und die obere globale Auswahl
  wurden entfernt.
- Strommonitor: Touchgeräte unterstützen Finger-Zoom und Verschieben.
- Strommonitor: Desktopgeräte unterstützen Rechteck-Zoom mit der Maus.
- Strommonitor: Legende, getrennte Achsen für A, V und W/kW sowie die Bedienung
  wurden für mobile Ansichten optimiert.
- Tests für Auswahl, Livewerte, Datenreihen, Zoom, Aktualisierung und
  responsive Darstellung wurden ergänzt.

## 0.1.2 – 2026-08-04

- GCP-Infrastruktur an das eigenständige GHCR-Deployment aus
  `deploy/production` angepasst.
- Repository-Checkout, lokales Produktions-Build und GCP-Compose-Override von
  der VM entfernt.
- Vorhandene GCP-Ressourcen können nun explizit referenziert oder kontrolliert
  in Terraform importiert werden; neue Ressourcen benötigen eigene
  Aktivierungsschalter.
- Idempotenten Bootstrap und alle persistenten Datenpfade unter
  `/srv/ga-server` vereinheitlicht.
- Terraform-, TFLint-, ShellCheck- und Secret-Prüfungen für die
  Infrastruktur-Pipeline erweitert.

## 0.1.1 – 2026-08-04

- Automatische, testgeschützte Veröffentlichung des GA-Server-Images in GHCR
  ergänzt.
- Unveränderliche Versions- und Commit-Tags sowie `latest` und `main` für den
  erfolgreichen Hauptbranch eingeführt.
- Multi-Architecture-Build für `linux/amd64` und `linux/arm64` eingerichtet.
- Eigenständigen Produktionsordner mit Image-basierter Compose-Konfiguration,
  Host-Persistenz, dateibasierten Secrets und gehärteten Containern ergänzt.
- Dokumentierte Image-Updates und Rollbacks ohne erneuten Checkout oder lokalen
  Build hinzugefügt.
- Produktions-Stack-Smoke-Test für Healthchecks, MQTT, Caddy, Ports, Secrets und
  Persistenz ergänzt.

## 0.1.0 – 2026-08-03

- GA-Server als Docker-basierte FastAPI-Anwendung angelegt.
- MQTT-Empfang für Shelly Pro 3EM implementiert.
- Dynamische Geräteverwaltung ergänzt.
- Strom, Spannung und Leistung für L1, L2 und L3 hinzugefügt.
- Fortlaufenden 24-Stunden-Graphen umgesetzt.
- Responsive Vollbildansicht für PC, Tablet und Mobilgeräte ergänzt.
- Öffentlichen Visualisierungsbereich und geschützten Administrationsbereich umgesetzt.
- Minutenmittelwerte sowie rollierende Min-/Max-Werte implementiert.
- Automatische Größenbegrenzung und Bereinigung der SQLite-Datenbank ergänzt.
- GCP-Deployment-Dokumentation und automatisierte Tests hinzugefügt.
