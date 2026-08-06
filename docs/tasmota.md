# Tasmota-Betrieb

Stand: GA-Server 0.3.0, 06.08.2026.

## Gerät anlegen

Beispiel Bauwagen:

- Anzeigename: `Bauwagen`
- technische Geräte-ID: `id139_bauwagen`
- Geräteart: `tasmota_plug`
- MQTT-Gerätetopic: `id139_bauwagen`
- MQTT-Client-ID: `DVES_5ED4C8`
- steuerbar: ja
- Relais: 1
- aktiv: ja

Im Gerätetopic dürfen weder `/` noch die Präfixe `cmnd/`, `stat/` oder `tele/`
stehen. Zugangsdaten werden mit Mosquitto-Werkzeugen verwaltet und erscheinen
nicht in HTML, JavaScript, Browser-Speichern, API-Antworten oder WebSockets.

## Datenfluss

GA-Server akzeptiert ausschließlich die klar klassifizierten Topics:

```text
tele/<topic>/SENSOR
tele/<topic>/LWT
stat/<topic>/STATUS10
stat/<topic>/POWER
stat/<topic>/RESULT
```

`ENERGY.Current`, `ENERGY.Voltage` und `ENERGY.Power` werden auf die
einphasigen L1- und Gesamtserien normalisiert. SENSOR und STATUS10 verwenden
anschließend denselben LiveStore und Minutenaggregator wie Shelly Pro 3EM.
Ungültiges JSON, boolesche Zahlen, NaN, Infinity, unbekannte Topics und
Payloads ohne Nutzwerte werden verworfen.

## Schalten

Der Browser sendet nur `on` oder `off` an die geschützte Admin-API. Der Server
erzeugt daraus:

```text
Topic:   cmnd/<topic>/POWER
Payload: ON oder OFF
QoS:     1
Retain:  false
```

Der Schalter bleibt bis zur passenden Meldung auf `stat/<topic>/POWER`
deaktiviert. Eine widersprüchliche Rückmeldung wird als tatsächlicher Zustand
übernommen und als Konflikt auditiert. Nach fünf Sekunden ohne Bestätigung
kehrt die Anzeige zum letzten bestätigten Zustand zurück. Offline-Geräte,
nicht freigegebene Geräte und parallele Befehle werden abgewiesen.

Nach jeder erfolgreichen Broker-Verbindung fragt GA-Server alle aktiven
Tasmota-Steckdosen mit einer leeren POWER-Payload ab.

## Diagnose

1. In „Systemstatus“ muss MQTT als verbunden erscheinen.
2. In der Steckdosen-Übersicht müssen Onlinezustand und Alter des Rohwertes
   plausibel sein.
3. `tele/<topic>/LWT` muss `Online` oder `Offline` liefern.
4. `stat/<topic>/POWER` muss `ON` oder `OFF` bestätigen.
5. Bei Timeout zuerst Topic, ACL und Tasmota-FullTopic prüfen.
6. Niemals Broker-Passwörter in Logs, Screenshots oder Tickets kopieren.

