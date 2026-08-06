# Migration und Rollback 0.3.0

## Vorbereitung

1. Anwendung stoppen oder ein Wartungsfenster verwenden.
2. Konsistentes SQLite-Backup einschließlich überprüfter Dateigröße anlegen.
3. Vorhandenen Release-Tag und Image-Digest notieren.
4. Migration zunächst auf einer Kopie der Produktionsdatenbank prüfen.

## Upgrade

```powershell
$env:GA_DATABASE_URL = "sqlite:///./data/ga-server-copy.db"
alembic upgrade head
alembic upgrade head
```

Migration `0002_tasmota_devices` prüft die vorhandenen Spalten und ergänzt nur
fehlende Felder:

```text
device_type VARCHAR(32) NOT NULL DEFAULT 'shelly_pro_3em'
controllable BOOLEAN NOT NULL DEFAULT 0
relay_index INTEGER NOT NULL DEFAULT 1
```

Zusätzlich wird `ix_devices_type_enabled` idempotent angelegt. Bestehende
Shelly-Geräte behalten ihre IDs, Topics, Messhistorie und ihr Verhalten.

Nach erfolgreichem Kopietest:

```powershell
alembic upgrade head
```

Anschließend `/health/ready`, Shelly-Livewerte, Historie, Anmeldung,
Steckdosen-Snapshot und einen kontrollierten Tasmota-Schaltvorgang prüfen.

## Rollback

Die neuen Spalten besitzen sichere Defaults und werden von Version 0.2.0
ignoriert. `alembic downgrade 0001_initial` entfernt deshalb nur den neuen
Index; SQLite-Spalten werden bewusst nicht durch einen riskanten Tabellenumbau
gelöscht.

Für einen vollständigen Rollback:

1. GA-Server stoppen.
2. Vorheriges Image beziehungsweise vorherigen Tag aktivieren.
3. Bei Bedarf das vor dem Upgrade erstellte SQLite-Backup zurückspielen.
4. Dateirechte prüfen und Anwendung starten.
5. Healthchecks, Shelly-Empfang, Historie und Wartungsjob kontrollieren.

Es gibt keine automatische Rückmigration produktiver Daten und kein Deployment
durch diese Anleitung.

