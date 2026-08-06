<!--
File: docs/architecture.md
Version: 0.3.0
Date: 2026-08-06
Purpose: Captures the application architecture, data paths, and explicit trade-offs.
-->

# Architekturentscheidung GA-Server 0.3.0

## Entscheidung

GA-Server ist ein modularer FastAPI-Monolith. HTTP, WebSocket, MQTT-Empfang,
Minutenaggregation und Wartungsjobs laufen in einem Prozess; Mosquitto und Caddy
bleiben getrennte Container. SQLite liegt auf einem persistenten Datenträger und
verwendet WAL.

## Datenfluss

1. Mosquitto nimmt TLS-Verbindungen auf `mqtt.strom.gruber-automation.de:8883` an.
2. GA-Server hält die bisherigen Shelly-Abonnements aktiv und abonniert getrennt
   die unterstützten Tasmota-Topics unter `tele/+/...` und `stat/+/...`.
3. Ein Shelly- und ein eigener Tasmota-Parser validieren Topic und Payload
   defensiv. Eine technische Geräte-ID
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
8. Der thread-sichere ControlStateStore hält bestätigten POWER-Zustand,
   Onlinezustand, Pending-Befehl, Deadline und letzten Fehler ausschließlich im
   RAM. DeviceControlService erzeugt serverseitig das MQTT-Topic und akzeptiert
   nur ON/OFF.
9. Control-Ereignisse laufen über einen eigenen sessiongeschützten WebSocket.
   Der öffentliche Live-WebSocket transportiert weiterhin nur Messwerte.

## Visualisierung

Der bestehende Canvas-Graph verwaltet alle aktivierten Kombinationen aus Gerät,
Messgröße und Phase als eigenständige Reihe. Strom, Spannung und Leistung
erhalten getrennte, beschriftete Skalen; Leistung wechselt bei passender
Größenordnung konsistent von W zu kW. Eine aus dem vollständigen Reihenschlüssel
deterministisch abgeleitete Farbe und ein phasenabhängiges Linienmuster werden
in Kurve, Legende und Tooltip gemeinsam verwendet.

Die Auswahl und der Aufbauzustand der eingebetteten Legende werden versioniert
im Browser gespeichert und beim Laden gegen die vom Server gemeldeten
Fähigkeiten validiert. Die Legende selbst startet geschlossen und wird mit dem
GA-Button bedient. Der Graph hält seinen Zeit-Zoom über Historienupdates hinweg.
Leere oder fehlgeschlagene Folgeantworten ersetzen keine gültigen Reihen.
Fehlende Minutenpunkte werden nicht zu Nullen umgedeutet; zeitliche
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
- MQTT-Benutzer werden in 0.3.0 über Mosquittos Passwortdatei verwaltet. Die
  Geräteverwaltung speichert keine abrufbaren Klartext-Passwörter.
- Caddy terminiert HTTPS; Mosquitto terminiert MQTT-TLS selbst.
- Die Referenzimplementierung `fronius-regler` war aus dieser Umgebung nicht
  abrufbar. Die beschriebenen Canvas- und Pufferprinzipien wurden unabhängig
  umgesetzt; Fronius-Fachlogik wurde nicht übernommen.
