<!--
File: deploy/gcp/terraform/README.md
Version: 0.1.0
Date: 2026-08-04
Purpose: Describes the reproducible GCP infrastructure deployment for GA-Server.
-->

# GA-Server auf GCP mit Terraform

Diese Konfiguration erstellt die Infrastruktur, startet die Anwendung aber bewusst
noch nicht mit Platzhalter-Secrets oder fehlenden MQTT-Zertifikaten.

## Erstellte Ressourcen

- eigene VPC und eigenes Subnetz in `europe-west3`
- Compute-Engine-VM `ga-server-01` mit Ubuntu 24.04 LTS
- statische externe IPv4-Adresse
- ausschließlich öffentliche Ports 80, 443 und 8883
- SSH nur über IAP aus `35.235.240.0/20`
- separate `pd-balanced`-Datendisk mit täglichem Snapshot
- privater GCS-Backup-Bucket mit Public Access Prevention und Lifecycle
- Secret-Manager-Secret `ga-mqtt-password` ohne im Terraform-State gespeicherten Secret-Wert
- dediziertes VM-Servicekonto mit minimalen Laufzeitrechten
- OS Login und Shielded VM

## Voraussetzungen

- vorhandenes GCP-Projekt mit aktivierter Abrechnung
- Berechtigung zum Aktivieren von APIs und Erstellen der Ressourcen
- Terraform 1.6 oder neuer
- zwei später gesetzte DNS-A-Records:
  `strom.gruber-automation.de` und `mqtt.strom.gruber-automation.de`

## Infrastruktur anlegen

```bash
cd deploy/gcp/terraform
cp terraform.tfvars.example terraform.tfvars
```

In `terraform.tfvars` mindestens `project_id` und `admin_members` ersetzen.
Während dieser gestapelten PR-Phase bleibt `repository_ref` auf
`agent/gcp-infrastructure`; nach dem Merge wird ein Release-Tag verwendet.

```bash
terraform init
terraform fmt -recursive
terraform validate
terraform plan -out=ga-server.tfplan
terraform apply ga-server.tfplan
terraform output
```

Der öffentliche IP-Wert aus `terraform output public_ip` wird anschließend für
beide DNS-A-Records verwendet. Die VM startet das Compose-System noch nicht,
sondern installiert Docker, bindet die Datendisk unter `/srv/ga-data` ein und
checkt das Repository nach `/opt/ga-server` aus.

## MQTT-Secret hinterlegen

Der Secret-Wert wird absichtlich separat eingespielt, damit er nicht in
`terraform.tfstate` landet:

```bash
printf '%s' '<starkes-internes-mqtt-passwort>' \
  | gcloud secrets versions add ga-mqtt-password \
      --project='<projekt-id>' \
      --data-file=-
```

## Verbindung zur VM

```bash
gcloud compute ssh ga-server-01 \
  --project='<projekt-id>' \
  --zone='europe-west3-a' \
  --tunnel-through-iap
```

Der exakte Befehl steht auch im Terraform-Output `iap_ssh_command`.

## Laufzeit vorbereiten

Auf der VM müssen vor dem ersten Start diese Dateien vorhanden sein:

```text
/srv/ga-data/mqtt/certs/ca.crt
/srv/ga-data/mqtt/certs/server.crt
/srv/ga-data/mqtt/certs/server.key
/srv/ga-data/mqtt/passwords
```

Das Serverzertifikat muss `mqtt.strom.gruber-automation.de` als SAN enthalten.
Danach:

```bash
cd /opt/ga-server
sudo ACME_EMAIL='admin@gruber-automation.de' \
  ./deploy/gcp/prepare-runtime.sh
```

Das Skript liest `ga-mqtt-password` über die VM-Identität aus Secret Manager,
erstellt die Produktionskonfiguration, prüft die Zertifikate und startet den
Compose-Stack mit persistenten Bind-Mounts auf der Datendisk.

Anschließend wird der erste Administrator interaktiv angelegt:

```bash
docker compose \
  -f docker-compose.yml \
  -f deploy/gcp/docker-compose.gcp.yml \
  exec ga-server python -m app.cli create-admin --username betreiber
```

## Prüfung

```bash
curl -fsS https://strom.gruber-automation.de/health/live
curl -fsS https://strom.gruber-automation.de/health/ready
docker compose \
  -f docker-compose.yml \
  -f deploy/gcp/docker-compose.gcp.yml \
  ps
```

## Wichtige Sicherheitsentscheidung

Port 22 ist nicht öffentlich freigegeben. Terraform erteilt den in
`admin_members` eingetragenen Identitäten IAP-Tunnel- und OS-Admin-Login-Rechte.
Port 1883 bleibt ausschließlich im Docker-Netz. Der GCS-Bucket blockiert
öffentlichen Zugriff. Secret-Werte werden weder committed noch über
Terraform-Variablen verarbeitet.
