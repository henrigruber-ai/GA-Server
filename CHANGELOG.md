<!--
File: CHANGELOG.md
Version: 0.2.0
Date: 2026-08-04
Purpose: Records user-visible changes by semantic version.
-->

# Versionshistorie

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
