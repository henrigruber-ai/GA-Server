# File: deploy/gcp/terraform/main.tf
# Version: 0.3.0
# Date: 2026-08-04
# Purpose: Safely creates or references explicitly selected GA-Server GCP resources.

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  network_name = var.create_network ? var.network_name : var.existing_network_name
  subnetwork_name = (
    var.create_subnetwork ? var.subnetwork_name : var.existing_subnetwork_name
  )
  static_ip_name = (
    var.create_static_ip ? var.static_ip_name : var.existing_static_ip_name
  )
  static_ip_address = (
    var.create_static_ip ? google_compute_address.public[0].address : var.existing_static_ip_address
  )
  service_account_email = (
    var.create_service_account
    ? google_service_account.vm[0].email
    : var.existing_service_account_email
  )
  mqtt_secret_name = (
    var.create_mqtt_secret ? var.mqtt_secret_name : var.existing_mqtt_secret_name
  )
  backup_bucket_name = (
    var.create_backup_bucket ? var.backup_bucket_name : var.existing_backup_bucket_name
  )
  data_disk_name = (
    var.create_data_disk ? var.data_disk_name : var.existing_data_disk_name
  )
  instance_output_name = (
    var.create_instance ? var.instance_name : var.existing_instance_name
  )
  common_labels = {
    application = "ga-server"
    environment = "production"
    managed_by  = "terraform"
  }
  required_services = toset([
    "compute.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])
}

check "explicit_resource_selection" {
  assert {
    condition     = local.network_name != null
    error_message = "Set network_name when create_network=true, otherwise existing_network_name."
  }

  assert {
    condition     = local.subnetwork_name != null
    error_message = "Set subnetwork_name when create_subnetwork=true, otherwise existing_subnetwork_name."
  }

  assert {
    condition     = !var.create_subnetwork || var.subnet_cidr != null
    error_message = "subnet_cidr is required when create_subnetwork=true."
  }

  assert {
    condition = (
      !var.create_static_ip ||
      (var.static_ip_name != null && var.static_ip_name != "")
    )
    error_message = "static_ip_name is required when create_static_ip=true."
  }

  assert {
    condition = (
      !var.create_service_account ||
      (var.service_account_id != null && var.service_account_id != "")
    )
    error_message = "service_account_id is required when create_service_account=true."
  }

  assert {
    condition = (
      !var.create_firewall_rules ||
      (
        var.public_firewall_rule_name != null &&
        var.iap_firewall_rule_name != null
      )
    )
    error_message = "Both firewall rule names are required when create_firewall_rules=true."
  }

  assert {
    condition = (
      !var.create_mqtt_secret ||
      (var.mqtt_secret_name != null && var.mqtt_secret_name != "")
    )
    error_message = "mqtt_secret_name is required when create_mqtt_secret=true."
  }

  assert {
    condition = (
      !var.enable_gcs_backups ||
      (var.create_backup_bucket ? var.backup_bucket_name != null : var.existing_backup_bucket_name != null)
    )
    error_message = "Select a new or existing backup bucket when enable_gcs_backups=true."
  }

  assert {
    condition     = !var.create_backup_bucket || var.enable_gcs_backups
    error_message = "create_backup_bucket requires enable_gcs_backups=true."
  }

  assert {
    condition = (
      !var.create_snapshot_policy ||
      (
        var.snapshot_policy_name != null &&
        local.data_disk_name != null
      )
    )
    error_message = "snapshot_policy_name and a selected data disk are required."
  }

  assert {
    condition = (
      !var.create_instance ||
      (
        var.instance_name != null &&
        local.data_disk_name != null &&
        local.static_ip_address != null &&
        var.public_base_url != null &&
        var.mqtt_public_host != null &&
        var.acme_email != null
      )
    )
    error_message = "A managed VM requires explicit instance, disk, IP, public URL, MQTT host and ACME email values."
  }
}

resource "google_project_service" "required" {
  for_each = var.manage_project_services ? local.required_services : toset([])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "main" {
  count = var.create_network ? 1 : 0

  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "main" {
  count = var.create_subnetwork ? 1 : 0

  name                     = var.subnetwork_name
  region                   = var.region
  network                  = local.network_name
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true

  depends_on = [google_compute_network.main]
}

resource "google_compute_address" "public" {
  count = var.create_static_ip ? 1 : 0

  name         = var.static_ip_name
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "vm" {
  count = var.create_service_account ? 1 : 0

  account_id   = var.service_account_id
  display_name = "GA-Server production VM"
  description  = "Least-privilege runtime identity for GA-Server."

  depends_on = [google_project_service.required]
}

resource "google_compute_firewall" "public_services" {
  count = var.create_firewall_rules ? 1 : 0

  name      = var.public_firewall_rule_name
  network   = local.network_name
  direction = "INGRESS"
  priority  = 1000

  source_ranges           = ["0.0.0.0/0"]
  target_service_accounts = [local.service_account_email]

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8883"]
  }

  allow {
    protocol = "udp"
    ports    = ["443"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }

  depends_on = [google_compute_network.main, google_service_account.vm]
}

resource "google_compute_firewall" "iap_ssh" {
  count = var.create_firewall_rules ? 1 : 0

  name      = var.iap_firewall_rule_name
  network   = local.network_name
  direction = "INGRESS"
  priority  = 1000

  source_ranges           = ["35.235.240.0/20"]
  target_service_accounts = [local.service_account_email]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }

  depends_on = [google_compute_network.main, google_service_account.vm]
}

resource "google_project_iam_member" "logging" {
  count = var.manage_runtime_iam ? 1 : 0

  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${local.service_account_email}"
}

resource "google_project_iam_member" "monitoring" {
  count = var.manage_runtime_iam ? 1 : 0

  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${local.service_account_email}"
}

resource "google_project_iam_member" "admin_iap" {
  for_each = var.manage_admin_iam ? var.admin_members : toset([])

  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = each.value
}

resource "google_project_iam_member" "admin_os_login" {
  for_each = var.manage_admin_iam ? var.admin_members : toset([])

  project = var.project_id
  role    = "roles/compute.osAdminLogin"
  member  = each.value
}

resource "google_secret_manager_secret" "mqtt_password" {
  count = var.create_mqtt_secret ? 1 : 0

  secret_id = var.mqtt_secret_name

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "vm_mqtt_password" {
  count = var.manage_runtime_iam && local.mqtt_secret_name != null ? 1 : 0

  project   = var.project_id
  secret_id = local.mqtt_secret_name
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_account_email}"

  depends_on = [google_secret_manager_secret.mqtt_password]
}

resource "google_storage_bucket" "backups" {
  count = var.create_backup_bucket ? 1 : 0

  name                        = var.backup_bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = var.backup_retention_days
    }
    action {
      type = "Delete"
    }
  }

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "vm_backups" {
  count = var.manage_runtime_iam && var.enable_gcs_backups ? 1 : 0

  bucket = local.backup_bucket_name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${local.service_account_email}"

  depends_on = [google_storage_bucket.backups]
}

resource "google_compute_disk" "data" {
  count = var.create_data_disk ? 1 : 0

  name = var.data_disk_name
  type = "pd-balanced"
  zone = var.zone
  size = var.data_disk_size_gb

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

resource "google_compute_resource_policy" "daily_snapshot" {
  count = var.create_snapshot_policy ? 1 : 0

  name   = var.snapshot_policy_name
  region = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "03:00"
      }
    }

    retention_policy {
      max_retention_days    = var.backup_retention_days
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }

    snapshot_properties {
      guest_flush       = true
      storage_locations = [var.region]
      labels            = local.common_labels
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_compute_disk_resource_policy_attachment" "data_snapshot" {
  count = var.create_snapshot_policy ? 1 : 0

  name = google_compute_resource_policy.daily_snapshot[0].name
  disk = local.data_disk_name
  zone = var.zone

  depends_on = [google_compute_disk.data]
}

data "google_compute_image" "ubuntu" {
  count = var.create_instance ? 1 : 0

  family  = "ubuntu-2404-lts-amd64"
  project = "ubuntu-os-cloud"
}

resource "google_compute_instance" "server" {
  count = var.create_instance ? 1 : 0

  name                      = var.instance_name
  machine_type              = var.machine_type
  zone                      = var.zone
  allow_stopping_for_update = true
  deletion_protection       = var.deletion_protection
  can_ip_forward            = false

  labels = local.common_labels

  boot_disk {
    auto_delete = true
    initialize_params {
      image  = data.google_compute_image.ubuntu[0].self_link
      size   = var.boot_disk_size_gb
      type   = "pd-balanced"
      labels = local.common_labels
    }
  }

  attached_disk {
    source      = "projects/${var.project_id}/zones/${var.zone}/disks/${local.data_disk_name}"
    device_name = var.data_disk_device_name
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = local.subnetwork_name
    network_ip = var.internal_ip

    access_config {
      nat_ip       = local.static_ip_address
      network_tier = "PREMIUM"
    }
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
    serial-port-enable     = "FALSE"
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    acme_email_b64          = base64encode(var.acme_email == null ? "" : var.acme_email)
    allow_disk_format       = var.allow_data_disk_format
    data_device_name_b64    = base64encode(var.data_disk_device_name)
    deployment_base_url_b64 = base64encode(var.deployment_source_base_url)
    deployment_ref_b64      = base64encode(var.deployment_source_ref)
    image_tag_b64           = base64encode(var.image_tag)
    mqtt_host_b64           = base64encode(var.mqtt_public_host == null ? "" : var.mqtt_public_host)
    mqtt_secret_name_b64    = base64encode(local.mqtt_secret_name == null ? "" : local.mqtt_secret_name)
    project_id_b64          = base64encode(var.project_id)
    public_base_url_b64     = base64encode(var.public_base_url == null ? "" : var.public_base_url)
  })

  service_account {
    email  = local.service_account_email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    provisioning_model  = "STANDARD"
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  depends_on = [
    google_compute_address.public,
    google_compute_disk.data,
    google_compute_disk_resource_policy_attachment.data_snapshot,
    google_compute_firewall.iap_ssh,
    google_compute_firewall.public_services,
    google_project_iam_member.logging,
    google_project_iam_member.monitoring,
    google_secret_manager_secret_iam_member.vm_mqtt_password,
    google_service_account.vm,
    google_storage_bucket_iam_member.vm_backups,
  ]
}
