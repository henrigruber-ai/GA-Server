<!--
File: CHANGELOG.md
Version: 0.1.1
Date: 2026-08-04
Purpose: Records user-visible changes by semantic version.
-->

# Versionshistorie

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
