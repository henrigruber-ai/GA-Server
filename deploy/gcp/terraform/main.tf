# File: deploy/gcp/terraform/main.tf
# Version: 0.1.0
# Date: 2026-08-04
# Purpose: Creates the production-ready GCP foundation for GA-Server.

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  name_prefix      = "ga-server-${var.environment}"
  backup_bucket    = coalesce(var.backup_bucket_name, "${var.project_id}-ga-server-backups")
  data_device_name = "ga-data"
  common_labels = {
    application = "ga-server"
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "compute.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "main" {
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "main" {
  name                     = "${local.name_prefix}-subnet"
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

resource "google_compute_address" "public" {
  name         = "${local.name_prefix}-public-ip"
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"

  depends_on = [google_project_service.required]
}

resource "google_compute_firewall" "public_services" {
  name      = "${local.name_prefix}-allow-public"
  network   = google_compute_network.main.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ga-server-public"]

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8883"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "iap_ssh" {
  name      = "${local.name_prefix}-allow-iap-ssh"
  network   = google_compute_network.main.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["ga-server-iap"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_service_account" "vm" {
  account_id   = "${local.name_prefix}-vm"
  display_name = "GA-Server ${var.environment} VM"
  description  = "Least-privilege runtime identity for GA-Server."

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "admin_iap" {
  for_each = var.admin_members

  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = each.value
}

resource "google_project_iam_member" "admin_os_login" {
  for_each = var.admin_members

  project = var.project_id
  role    = "roles/compute.osAdminLogin"
  member  = each.value
}

resource "google_secret_manager_secret" "mqtt_password" {
  secret_id = "ga-mqtt-password"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "vm_mqtt_password" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.mqtt_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_storage_bucket" "backups" {
  name                        = local.backup_bucket
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
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_compute_disk" "data" {
  name = "${local.name_prefix}-data"
  type = "pd-balanced"
  zone = var.zone
  size = var.data_disk_size_gb

  labels = local.common_labels

  depends_on = [google_project_service.required]
}

resource "google_compute_resource_policy" "daily_snapshot" {
  name   = "${local.name_prefix}-daily-snapshot"
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
  name = google_compute_resource_policy.daily_snapshot.name
  disk = google_compute_disk.data.name
  zone = var.zone
}

data "google_compute_image" "ubuntu" {
  family  = "ubuntu-2404-lts-amd64"
  project = "ubuntu-os-cloud"
}

resource "google_compute_instance" "server" {
  name                      = var.instance_name
  machine_type              = var.machine_type
  zone                      = var.zone
  allow_stopping_for_update = true
  deletion_protection       = var.deletion_protection
  can_ip_forward            = false

  tags   = ["ga-server-public", "ga-server-iap"]
  labels = local.common_labels

  boot_disk {
    auto_delete = true
    initialize_params {
      image  = data.google_compute_image.ubuntu.self_link
      size   = var.boot_disk_size_gb
      type   = "pd-balanced"
      labels = local.common_labels
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = local.data_device_name
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
    network_ip = cidrhost(var.subnet_cidr, 10)

    access_config {
      nat_ip       = google_compute_address.public.address
      network_tier = "PREMIUM"
    }
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
    serial-port-enable     = "FALSE"
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    data_device_name = local.data_device_name
    repository_url   = var.repository_url
    repository_ref   = var.repository_ref
  })

  service_account {
    email  = google_service_account.vm.email
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
    google_compute_disk_resource_policy_attachment.data_snapshot,
    google_project_iam_member.logging,
    google_project_iam_member.monitoring,
    google_secret_manager_secret_iam_member.vm_mqtt_password,
    google_storage_bucket_iam_member.vm_backups,
  ]
}
