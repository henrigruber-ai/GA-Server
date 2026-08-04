<!--
File: deploy/gcp/README.md
Version: 0.2.0
Date: 2026-08-04
Purpose: Operates GA-Server on GCP from published images without a source checkout.
-->

# GCP-Betriebshandbuch

GA-Server läuft auf der VM ausschließlich mit den Dateien aus
`deploy/production` und fertigen Images aus
`ghcr.io/henrigruber-ai/ga-server`. Python-Quellcode, Root-Compose,
GCP-Compose-Overrides, `git pull`, `docker compose build` und ein Terraform-Lauf
für normale Anwendungsupdates sind nicht erforderlich.

Bekannte Umgebung:

```text
Projekt:             gruber-ga-server-prod
VPC:                 ga-server-vpc
Laufzeitidentität:   ga-server-vm@gruber-ga-server-prod.iam.gserviceaccount.com
```

Unbekannte Namen bleiben als `<ZONE>`, `<SUBNET_NAME>`, `<VM_NAME>`,
`<STATIC_IP_NAME>` und `<DATA_DISK_NAME>` markiert.

## 1. Infrastrukturvarianten

### Vollständig neu

Alle Namen werden vorab festgelegt und die benötigten `create_*`-Schalter
explizit aktiviert. Eine neue VM verwendet Ubuntu 24.04 LTS, Shielded VM mit
Secure Boot, vTPM und Integrity Monitoring, OS Login, blockierte
projektweite SSH-Schlüssel, eine separate Balanced-PD und optional tägliche
Snapshots sowie einen privaten GCS-Bucket. Die vollständige Konfiguration steht
in [`terraform/README.md`](terraform/README.md#vollständig-neue-infrastruktur).

### Teilweise vorhanden

Vorhandene VPC, Subnetz, Servicekonto, statische IP und Datendisk werden über
`existing_*` referenziert. Neue Ressourcen bleiben deaktiviert. Damit erzeugt
ein Plan keine parallelen Namen wie `ga-server-prod-vpc` oder
`ga-server-prod-vm`.

```bash
cd deploy/gcp/terraform
cp terraform.tfvars.example terraform.tfvars
# Alle <PLATZHALTER> durch verifizierte Werte ersetzen.
terraform init
terraform validate
terraform plan
```

Erwartung für eine vollständig referenzierte, manuell verwaltete Umgebung:
keine Ressourcenaktionen (`0 to add, 0 to change, 0 to destroy`). Bei leerem
State dürfen nur neue Output-Werte erscheinen.

### Bereits vorhanden und künftig durch Terraform verwaltet

Die Ressource wird zuerst mit ihren realen Eigenschaften konfiguriert, ihr
`create_*`-Schalter aktiviert und dann importiert. Import-Adressen, GCP-IDs und
die zwingende Plan-Kontrolle stehen in
[`terraform/README.md`](terraform/README.md#vorhandene-ressourcen-importieren).
Ein Import verändert die Ressource nicht. Ein Apply ist erst nach einem leeren,
menschlich geprüften Plan zulässig und gehört nicht zu diesem Arbeitsablauf.

## 2. Netzwerk und Firewall

Öffentlich erlaubt:

- TCP 80 und 443 für HTTP, ACME und HTTPS
- UDP 443 für HTTP/3
- TCP 8883 für MQTT über TLS

Nicht öffentlich:

- TCP 22; SSH ausschließlich über IAP aus `35.235.240.0/20`
- TCP 1883; nur internes Container-Netz
- TCP 8000; nur Caddy zum Anwendungscontainer
- TCP 2019; nur lokaler Caddy-Admin-Endpunkt

Die Terraform-Regeln besitzen Firewall-Logging und zielen auf das ausgewählte
Laufzeit-Servicekonto statt auf allgemeine Netzwerk-Tags. Projektweite
SSH-Schlüssel sind auf der VM blockiert; OS Login ist aktiviert.

## 3. DNS

Terraform ändert kein DNS. Nach Prüfung der statischen IP werden zwei A-Records
manuell benötigt:

```text
<PUBLIC_HOSTNAME>  -> <STATIC_IP_ADDRESS>
<MQTT_HOSTNAME>    -> <STATIC_IP_ADDRESS>
```

Vor dem ersten Start müssen beide Namen öffentlich korrekt auflösen. Die
Website verwendet `https://<PUBLIC_HOSTNAME>`, Shelly-Geräte verwenden
`<MQTT_HOSTNAME>:8883`.

## 4. Erstinstallation auf neuer oder vorhandener VM

Der Bootstrap ist idempotent und:

- installiert Docker Engine und das Compose-Plugin,
- mountet die Datendisk unter `/srv/ga-server`,
- lädt ausschließlich versionierte Produktionsdateien,
- bewahrt vorhandene `.env`, Secrets, Passwörter, Zertifikate und Daten,
- liest optional genau ein MQTT-Secret mit der VM-Identität,
- validiert Konfiguration, Rechte und Zertifikate,
- führt `docker compose config`, `pull`, `up -d --remove-orphans`, `ps` und
  einen Readiness-Check aus.

Eine unformatierte Disk wird nur mit der expliziten Einstellung
`GA_ALLOW_DATA_DISK_FORMAT=true` formatiert. Für vorhandene Disks bleibt sie
`false`.

Bei einer Terraform-verwalteten neuen VM wird der Bootstrap als
Startup-Skript installiert. Auf einer vorhandenen, nicht importierten VM:

```bash
gcloud compute ssh <VM_NAME> \
  --project=gruber-ga-server-prod \
  --zone=<ZONE> \
  --tunnel-through-iap
```

Dann einen unveränderlichen Release-Tag oder vollständigen Commit verwenden:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/henrigruber-ai/GA-Server/v0.2.0/deploy/gcp/bootstrap.sh \
  -o /tmp/ga-server-bootstrap.sh
chmod 0755 /tmp/ga-server-bootstrap.sh

sudo \
  GA_PROJECT_ID=gruber-ga-server-prod \
  GA_DATA_DEVICE_NAME=<ATTACHED_DEVICE_NAME> \
  GA_ALLOW_DATA_DISK_FORMAT=false \
  GA_DEPLOYMENT_SOURCE_REF=v0.2.0 \
  GA_SERVER_IMAGE_TAG=0.2.0 \
  GA_MQTT_SECRET_NAME=<MQTT_SECRET_NAME> \
  GA_PUBLIC_BASE_URL=https://<PUBLIC_HOSTNAME> \
  GA_MQTT_PUBLIC_HOST=<MQTT_HOSTNAME> \
  GA_ACME_EMAIL=<ACME_EMAIL> \
  /tmp/ga-server-bootstrap.sh
```

Beim ersten Lauf darf das Skript wegen noch fehlender manueller Zertifikate
kontrolliert abbrechen. Nach Bereitstellung der Dateien denselben Befehl erneut
ausführen. Es werden keine vorhandenen Werte überschrieben.

## 5. Persistente Verzeichnisse und Rechte

```text
/srv/ga-server/app                         10001:10001, 0750
/srv/ga-server/backups                     root:root, 0700
/srv/ga-server/caddy/data                  root:root, 0750
/srv/ga-server/caddy/config                root:root, 0750
/srv/ga-server/mosquitto/data              1883:1883, 0750
/srv/ga-server/mosquitto/log               1883:1883, 0750
/srv/ga-server/mqtt/certs                  root:1883, 0750
/srv/ga-server/mqtt/config                 root:1883, 0750
/srv/ga-server/secrets                     root:root, 0700
```

Ein `docker compose up --force-recreate` oder `down` löscht diese Bind-Mount-
Daten nicht. Die frühere parallele Struktur `/srv/ga-data` wird nicht mehr
verwendet.

## 6. Manuelle Secrets und Zertifikate

Nie committen, in Terraform-Variablen schreiben oder in Logs ausgeben:

```text
/srv/ga-server/secrets/ga_mqtt_password
/srv/ga-server/mqtt/config/passwords
/srv/ga-server/mqtt/certs/ca.crt
/srv/ga-server/mqtt/certs/server.crt
/srv/ga-server/mqtt/certs/server.key
```

Das Klartextpasswort wird im Container über
`GA_MQTT_PASSWORD_FILE=/run/secrets/ga_mqtt_password` gelesen. Falls
`GA_MQTT_SECRET_NAME` gesetzt ist, benötigt das Laufzeit-Servicekonto nur
`roles/secretmanager.secretAccessor` auf genau dieses Secret. Terraform
verwaltet keine Secret-Version und speichert keinen Secret-Wert im State.

Der Bootstrap erstellt die gehashte Mosquitto-Datenbank nur dann aus dem
vorhandenen Secret, wenn die Datei noch fehlt. Er erzeugt kein Passwort und
überschreibt weder Secret noch Passwortdatenbank. Weitere MQTT-Benutzer werden
interaktiv mit `mosquitto_passwd` ergänzt.

Rechte:

```bash
sudo chown 10001:1883 /srv/ga-server/secrets/ga_mqtt_password
sudo chmod 0440 /srv/ga-server/secrets/ga_mqtt_password
sudo chown root:1883 /srv/ga-server/mqtt/config/passwords
sudo chmod 0640 /srv/ga-server/mqtt/config/passwords
sudo chown root:1883 /srv/ga-server/mqtt/certs/*
sudo chmod 0644 /srv/ga-server/mqtt/certs/ca.crt \
  /srv/ga-server/mqtt/certs/server.crt
sudo chmod 0640 /srv/ga-server/mqtt/certs/server.key
```

Das MQTT-Serverzertifikat muss `<MQTT_HOSTNAME>` als SAN enthalten. Caddy
verwaltet sein Website-Zertifikat selbst und bewahrt ACME-Daten persistent auf.

## 7. GHCR öffentlich oder privat

Bevorzugt ist ein öffentlich lesbares Paket. Dann genügt:

```bash
docker pull ghcr.io/henrigruber-ai/ga-server:0.2.0
```

Bei einem privaten Paket wird ein ausschließlich mit `read:packages`
ausgestattetes Token außerhalb von `.env` und Terraform interaktiv eingelesen:

```bash
read -rsp 'GHCR token: ' GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" | sudo docker login ghcr.io \
  -u <GITHUB_USERNAME> --password-stdin
unset GHCR_TOKEN
sudo chmod 0600 /root/.docker/config.json
```

Token niemals committen, als Terraform-Variable übergeben oder in einem Befehl
direkt ausschreiben. Eine organisatorisch verfügbare Docker-Credential-Hilfe
ist einer langfristigen Token-Ablage vorzuziehen.

## 8. Image-Tags und normales Update

Unterstützt:

- `latest` und `main`: beweglich; folgen erfolgreichen Main-Builds.
- `sha-<commit>`: auf einen konkreten Commit rückführbar und für kontrollierte
  Rollbacks geeignet.
- `0.2.0`: Release-Version; für Produktion bevorzugt und als unveränderlicher
  Veröffentlichungsstand zu behandeln.

Normales Update ohne Terraform, Git und Build:

```bash
cd /opt/ga-server-production
docker compose config
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
curl --fail https://<PUBLIC_HOSTNAME>/health/ready
```

Ändert sich die Deployment-Konfiguration selbst, wird der Bootstrap mit einem
neuen fixierten `GA_DEPLOYMENT_SOURCE_REF` erneut ausgeführt. `.env` bleibt
bewusst unverändert.

## 9. Rollback

Vorheriges Image in `/opt/ga-server-production/.env` setzen:

```text
GA_SERVER_IMAGE=ghcr.io/henrigruber-ai/ga-server:sha-<PREVIOUS_COMMIT>
```

Dann:

```bash
docker compose config
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
curl --fail https://<PUBLIC_HOSTNAME>/health/ready
```

Ein Image-Rollback ändert keine Datenbank zurück. Bei nicht
rückwärtskompatiblen Migrationen ist zusätzlich das zum Release passende
konsistente SQLite-Backup nötig; kein blindes `alembic downgrade`.

## 10. Backup und Restore

Vier Mechanismen sind getrennt zu behandeln:

- Disk-Snapshot: Crash-konsistenter Stand der gesamten Datendisk; schnell für
  Infrastruktur-Recovery, aber kein Ersatz für ein geprüftes SQLite-Backup.
- SQLite-Backup: Mit `sqlite3.Connection.backup` erzeugter konsistenter
  Datenbankstand trotz WAL-Betrieb.
- GCS-Backup: Externe, zugriffsgeschützte Kopie eines konsistenten Backups mit
  Versionierung und Lifecycle; nicht die laufende DB-Datei blind kopieren.
- Image-Rollback: Wechselt nur Anwendungsbits und ersetzt keinen DB-Restore.

Restore ausschließlich in einem Wartungsfenster:

1. Gewünschten Wiederherstellungspunkt dokumentieren.
2. `docker compose stop ga-server`.
3. Aktuelle DB, WAL und SHM zusätzlich sichern.
4. Konsistentes Backup als `/srv/ga-server/app/ga-server.db` einspielen.
5. Eigentümer `10001:10001` und restriktive Rechte prüfen.
6. `docker compose start ga-server`.
7. Readiness, Logs, Benutzer, Geräte und Historie prüfen.

Restore-Tests vierteljährlich auf einer separaten VM durchführen, niemals
destruktiv gegen echte Produktionsdaten.

## 11. Logs, Healthchecks und Betrieb

```bash
cd /opt/ga-server-production
docker compose ps
docker compose logs --tail 200 ga-server
docker compose logs --tail 200 mosquitto
docker compose logs --tail 200 caddy
curl -fsS https://<PUBLIC_HOSTNAME>/health/live
curl -fsS https://<PUBLIC_HOSTNAME>/health/ready
docker stats --no-stream
df -h /srv/ga-server
sudo journalctl -u google-startup-scripts.service --no-pager
```

Der erste Administrator wird interaktiv angelegt:

```bash
docker compose exec ga-server \
  python -m app.cli create-admin --username betreiber
```

Wichtige Alarme: fehlerhafte Readiness, wenig freier Diskplatz,
Container-Neustarts, ausbleibende MQTT-Nachrichten und ablaufende Zertifikate.
