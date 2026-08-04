<!--
File: docs/architecture.md
Version: 0.1.0
Date: 2026-08-03
Purpose: Captures the MVP architecture and its explicit trade-offs.
-->

# Architekturentscheidung GA-Server 0.1.0

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
4. Ein begrenzter RAM-Puffer versorgt die Live-API und WebSockets.
5. Ein Aggregator schreibt je Gerät und UTC-Minute höchstens eine Zeile mit
   Anzahl, Mittelwert, Minimum und Maximum.
6. Öffentliche Lese-Endpunkte liefern begrenzte Ergebnisse. Schreibzugriffe
   liegen ausschließlich unter der session- und CSRF-geschützten Admin-API.

## Begründung

Ein Monolith hält Betrieb und Backups auf einer kleinen Compute-Engine-VM
überschaubar. Die fachlichen Komponenten bleiben dennoch getrennt und können
später ohne Änderung der API-Grenzen ausgelagert werden. SQLite reicht für wenige
Shelly-Geräte mit Minutenaggregation aus; Rohdaten werden bewusst nicht dauerhaft
gespeichert.

## Betriebsgrenzen

- Eine einzelne GA-Server-Instanz ist der Writer der SQLite-Datei.
- Der Live-Puffer ist absichtlich flüchtig.
- MQTT-Benutzer werden in 0.1.0 über Mosquittos Passwortdatei verwaltet. Die
  Geräteverwaltung speichert keine abrufbaren Klartext-Passwörter.
- Caddy terminiert HTTPS; Mosquitto terminiert MQTT-TLS selbst.
- Die Referenzimplementierung `fronius-regler` war aus dieser Umgebung nicht
  abrufbar. Die beschriebenen Canvas- und Pufferprinzipien wurden unabhängig
  umgesetzt; Fronius-Fachlogik wurde nicht übernommen.
