<!--
File: secrets/README.md
Version: 0.1.0
Date: 2026-08-03
Purpose: Explains runtime secret files without containing credentials.
-->

# Lokale Secret-Dateien

Lege vor `docker compose up` die Datei `secrets/ga_mqtt_password` an. Sie enthält
nur das interne Broker-Passwort des GA-Server-Clients und wird durch `.gitignore`
nicht versioniert.

Die öffentliche Mosquitto-Passwortdatei wird mit `mosquitto_passwd` in
`mosquitto/config/passwords` gepflegt. Die versionierte Datei ist absichtlich
leer und enthält keine Zugangsdaten.
