<!--
File: docs/architecture.md
Version: 0.2.0
Date: 2026-08-04
Purpose: Captures the application architecture, data paths, and explicit trade-offs.
-->

# Architekturentscheidung GA-Server 0.2.0

## Entscheidung

GA-Server ist ein modularer FastAPI-Monolith. HTTP, WebSocket, MQTT-Empfang,
Minutenaggregation und Wartungsjobs laufen in einem Prozess; Mosquitto und Caddy
bleiben getrennte Container. SQLite liegt auf einem persistenten Datenträger und
verwendet WAL.

## Datenfluss

1. Mosquitto nimmt TLS-Verbindungen auf `mqtt.strom.gruber-automation.de:8883` an.
2. GA-Server abonniert intern `ga/devices/+/status/em:0` und
   `ga/devices/+/online`.
3. Der Parser validiert Topic und Payload defensiv. Eine technische Geräte-ID
   wird genau einem konfigurierten Gerät zugeordnet.
4. Ein begrenzter RAM-Puffer versorgt die Live-API und WebSockets. Der jeweils
   letzte unveränderte Rohdatensatz je Gerät bildet die Datenquelle für die
   sekündlich neu dargestellten Legendenwerte.
5. Ein Aggregator schreibt je Gerät und UTC-Minute höchstens eine Zeile mit
   Anzahl, Mittelwert, Minimum und Maximum.
6. Öffentliche Lese-Endpunkte liefern begrenzte Ergebnisse. Schreibzugriffe
   liegen ausschließlich unter der session- und CSRF-geschützten Admin-API.
7. Die gebündelte Historien-API liest mehrere Messgrößen und Phasen in einer
   Anfrage aus den Minutenaggregaten. Der Browser aktualisiert diese Daten etwa
   alle zehn Sekunden unabhängig vom Rohwert-WebSocket.

## Visualisierung

Der bestehende Canvas-Graph verwaltet alle aktivierten Kombinationen aus Gerät,
Messgröße und Phase als eigenständige Reihe. Strom, Spannung und Leistung
erhalten getrennte, beschriftete Skalen; Leistung wechselt bei passender
Größenordnung konsistent von W zu kW. Eine aus dem vollständigen Reihenschlüssel
deterministisch abgeleitete Farbe und ein phasenabhängiges Linienmuster werden
in Kurve, Legende und Tooltip gemeinsam verwendet.

Die Auswahl und der Aufbauzustand der eingebetteten Legende werden versioniert
im Browser gespeichert und beim Laden gegen die vom Server gemeldeten
Fähigkeiten validiert. Der Graph hält seinen Zeit-Zoom über Historienupdates
hinweg. Fehlende Minutenpunkte werden nicht zu Nullen umgedeutet; zeitliche
Lücken von mehr als zweieinhalb Minuten unterbrechen die Linie.

## Begründung

Ein Monolith hält Betrieb und Backups auf einer kleinen Compute-Engine-VM
überschaubar. Die fachlichen Komponenten bleiben dennoch getrennt und können
später ohne Änderung der API-Grenzen ausgelagert werden. SQLite reicht für wenige
Shelly-Geräte mit Minutenaggregation aus; Rohdaten werden bewusst nicht dauerhaft
gespeichert.

## Betriebsgrenzen

- Eine einzelne GA-Server-Instanz ist der Writer der SQLite-Datei.
- Der Live-Puffer ist absichtlich flüchtig.
- MQTT-Benutzer werden in 0.2.0 über Mosquittos Passwortdatei verwaltet. Die
  Geräteverwaltung speichert keine abrufbaren Klartext-Passwörter.
- Caddy terminiert HTTPS; Mosquitto terminiert MQTT-TLS selbst.
- Die Referenzimplementierung `fronius-regler` war aus dieser Umgebung nicht
  abrufbar. Die beschriebenen Canvas- und Pufferprinzipien wurden unabhängig
  umgesetzt; Fronius-Fachlogik wurde nicht übernommen.
