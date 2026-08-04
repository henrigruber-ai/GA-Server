<!--
File: deploy/gcp/terraform/README.md
Version: 0.1.2
Date: 2026-08-04
Purpose: Documents safe creation, reuse, import and planning of GCP resources.
-->

# Terraform für GA-Server auf GCP

Diese Konfiguration verwaltet ausschließlich die ausdrücklich aktivierten
Ressourcen im Projekt `gruber-ga-server-prod`. Alle `create_*`- und
`manage_*`-Schalter sind standardmäßig `false`. Dadurch plant die
Beispielkonfiguration keine zweite VPC, kein zweites Servicekonto und keine
Ressourcen mit automatisch erfundenen Namen wie `ga-server-prod-vpc`,
`ga-server-prod-subnet` oder `ga-server-prod-vm`.

Terraform enthält keine Secret-Werte. Ein `plan` oder `import` verändert keine
GCP-Ressource; nur ein späteres, separat freigegebenes `apply` könnte Änderungen
ausführen.

## Steuerungsmodell

Für jede Ressourcengruppe gilt genau eines der beiden Modelle:

- `create_*=false`: vorhandenen Namen beziehungsweise vorhandene IP direkt
  referenzieren; Terraform verwaltet diese Ressource nicht.
- `create_*=true`: die Ressource mit explizitem Namen neu anlegen oder eine
  bereits vorhandene Ressource zuerst an dieselbe Terraform-Adresse importieren.

IAM- und API-Verwaltung sind zusätzlich über `manage_runtime_iam`,
`manage_admin_iam` und `manage_project_services` abgeschaltet. Vorhandene
manuelle Bindings werden dadurch nicht ungeprüft dupliziert.

Bekannte Werte sind vorbelegt:

```hcl
project_id                       = "gruber-ga-server-prod"
existing_network_name            = "ga-server-vpc"
existing_service_account_email   = "ga-server-vm@gruber-ga-server-prod.iam.gserviceaccount.com"
```

Alle noch unbekannten Namen müssen als `<...>` ersetzt werden.

## Teilweise vorhandene Infrastruktur sicher planen

```bash
cd deploy/gcp/terraform
cp terraform.tfvars.example terraform.tfvars
```

Zuerst die unbekannten Werte ausschließlich lesend ermitteln:

```bash
gcloud compute networks list --project=gruber-ga-server-prod
gcloud compute networks subnets list --project=gruber-ga-server-prod
gcloud compute addresses list --project=gruber-ga-server-prod
gcloud compute instances list --project=gruber-ga-server-prod
gcloud compute disks list --project=gruber-ga-server-prod
gcloud secrets list --project=gruber-ga-server-prod
gcloud storage buckets list --project=gruber-ga-server-prod
```

Danach `<ZONE>`, `<SUBNET_NAME>`, `<STATIC_IP_NAME>`,
`<STATIC_IP_ADDRESS>`, `<VM_NAME>`, `<DATA_DISK_NAME>` und gegebenenfalls
Secret- oder Bucket-Namen ersetzen. Die Schalter bleiben `false`:

```bash
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan
```

Der Plan darf keine Ressourcenaktionen enthalten (`0 to add, 0 to change,
0 to destroy`). Bei einem noch leeren State können ausschließlich neue
Output-Werte angezeigt werden. Er darf insbesondere keine parallele VPC, kein
zweites Servicekonto, keine VM und keine Datendisk erzeugen. Abweichungen
werden untersucht; es folgt kein automatisches Apply.

## Vollständig neue Infrastruktur

Für eine neue Umgebung werden nur die tatsächlich gewünschten Gruppen
aktiviert. Ressourcennamen sind bewusst Pflichtangaben:

```hcl
create_network = true
network_name   = "<NEW_VPC_NAME>"

create_subnetwork = true
subnetwork_name   = "<NEW_SUBNET_NAME>"
subnet_cidr       = "<NEW_SUBNET_CIDR>"

create_service_account = true
service_account_id     = "<NEW_SERVICE_ACCOUNT_ID>"

create_static_ip = true
static_ip_name   = "<NEW_STATIC_IP_NAME>"

create_firewall_rules      = true
public_firewall_rule_name  = "<PUBLIC_FIREWALL_RULE_NAME>"
iap_firewall_rule_name     = "<IAP_FIREWALL_RULE_NAME>"

create_data_disk       = true
data_disk_name         = "<NEW_DATA_DISK_NAME>"
allow_data_disk_format = true

create_snapshot_policy = true
snapshot_policy_name   = "<NEW_SNAPSHOT_POLICY_NAME>"

create_mqtt_secret = true
mqtt_secret_name   = "<MQTT_SECRET_NAME>"

create_instance = true
instance_name   = "<NEW_VM_NAME>"

manage_project_services = true
manage_runtime_iam      = true
manage_admin_iam        = true
admin_members           = ["user:<ADMIN_EMAIL>"]

public_base_url  = "https://<PUBLIC_HOSTNAME>"
mqtt_public_host = "<MQTT_HOSTNAME>"
acme_email       = "<ACME_EMAIL>"
```

Ein neuer GCS-Bucket ist optional und benötigt einen global eindeutigen,
expliziten Namen:

```hcl
enable_gcs_backups  = true
create_backup_bucket = true
backup_bucket_name   = "<GLOBALLY_UNIQUE_BUCKET_NAME>"
```

`allow_data_disk_format=true` ist nur für eine nachweislich neue, leere Disk
zulässig. Bei vorhandenen oder importierten Disks bleibt der Wert `false`.

## Vorhandene Ressourcen importieren

Ein Import nimmt eine vorhandene Ressource nur in den Terraform-State auf. Er
ändert, startet, stoppt oder löscht sie nicht. Vor jedem Import:

1. Ressource mit den obigen `gcloud ... list/describe`-Befehlen identifizieren.
2. Den zugehörigen `create_*`-Schalter auf `true` setzen und alle Attribute an
   die reale Ressource angleichen.
3. Remote-State beziehungsweise lokalen State sichern.
4. Genau eine der folgenden Adressen importieren.

```bash
terraform import \
  'google_compute_network.main[0]' \
  'projects/gruber-ga-server-prod/global/networks/<VPC_NAME>'

terraform import \
  'google_compute_subnetwork.main[0]' \
  'projects/gruber-ga-server-prod/regions/<REGION>/subnetworks/<SUBNET_NAME>'

terraform import \
  'google_compute_address.public[0]' \
  'projects/gruber-ga-server-prod/regions/<REGION>/addresses/<STATIC_IP_NAME>'

terraform import \
  'google_service_account.vm[0]' \
  'projects/gruber-ga-server-prod/serviceAccounts/<SERVICE_ACCOUNT_EMAIL>'

terraform import \
  'google_compute_firewall.public_services[0]' \
  'projects/gruber-ga-server-prod/global/firewalls/<PUBLIC_FIREWALL_RULE_NAME>'

terraform import \
  'google_compute_firewall.iap_ssh[0]' \
  'projects/gruber-ga-server-prod/global/firewalls/<IAP_FIREWALL_RULE_NAME>'

terraform import \
  'google_secret_manager_secret.mqtt_password[0]' \
  'projects/gruber-ga-server-prod/secrets/<MQTT_SECRET_NAME>'

terraform import \
  'google_storage_bucket.backups[0]' \
  'gruber-ga-server-prod/<BACKUP_BUCKET_NAME>'

terraform import \
  'google_compute_disk.data[0]' \
  'projects/gruber-ga-server-prod/zones/<ZONE>/disks/<DATA_DISK_NAME>'

terraform import \
  'google_compute_resource_policy.daily_snapshot[0]' \
  'projects/gruber-ga-server-prod/regions/<REGION>/resourcePolicies/<SNAPSHOT_POLICY_NAME>'

terraform import \
  'google_compute_disk_resource_policy_attachment.data_snapshot[0]' \
  'projects/gruber-ga-server-prod/zones/<ZONE>/disks/<DATA_DISK_NAME>/<SNAPSHOT_POLICY_NAME>'

terraform import \
  'google_compute_instance.server[0]' \
  'projects/gruber-ga-server-prod/zones/<ZONE>/instances/<VM_NAME>'
```

Nicht jede vorhandene Ressource muss importiert werden. VPC, Subnetz,
Servicekonto, IP, Disk oder VM können mit `create_*=false` weiter manuell
verwaltet und nur referenziert werden.

Nach jedem Import:

```bash
terraform state show '<TERRAFORM_ADDRESS>'
terraform plan
```

Ein sauberer Plan ist leer. Bei einer importierten VM sind Boot-Image,
Maschinentyp, Disk-Anbindung, Netzwerk, Metadaten, Servicekonto, Shielded-VM-
Optionen und Löschschutz besonders sorgfältig abzugleichen. Ein Plan mit
`replace`, `destroy`, Stoppen der VM oder unerwarteten Änderungen wird nicht
angewendet. Erst nach menschlicher Prüfung und separater Freigabe wäre ein
`apply` zulässig; diese Anleitung führt keines aus.

Die verwendeten Import-ID-Formate entsprechen der offiziellen Dokumentation
des [Google-Terraform-Providers](https://registry.terraform.io/providers/hashicorp/google/latest/docs).

## Bootstrap-Konfiguration

Eine Terraform-verwaltete VM lädt `deploy/gcp/bootstrap.sh` aus
`deployment_source_ref` und anschließend nur diese Dateien:

```text
deploy/production/docker-compose.yml
deploy/production/Caddyfile
deploy/production/mosquitto.conf
deploy/production/update.sh
deploy/production/.env.example
```

Für Produktion wird ein unveränderlicher Release-Tag oder vollständiger
Commit-SHA verwendet. `v0.1.2` ist die Konfigurationsversion; `image_tag`
steuert unabhängig davon das GHCR-Image. Es gibt weder Repository-Checkout noch
lokalen Docker-Build.

Beim Import einer laufenden VM kann eine Änderung von
`metadata_startup_script` einen relevanten Plan erzeugen. Dieser Plan wird
nicht blind angewendet. Alternativ bleibt `create_instance=false` und der
Betreiber führt den dokumentierten Bootstrap kontrolliert per IAP aus.

## Verbotene Befehle in diesem Arbeitsablauf

```text
terraform apply
terraform destroy
terraform import (ohne explizite Betreiberentscheidung)
```

CI führt ausschließlich Formatierung, `init -backend=false`, Validierung,
TFLint, ShellCheck und die Secret-Mustersuche aus.
