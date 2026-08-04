# File: deploy/gcp/terraform/variables.tf
# Version: 0.1.2
# Date: 2026-08-04
# Purpose: Controls explicit creation, reuse and import of GA-Server GCP resources.

variable "project_id" {
  description = "Existing GCP project ID."
  type        = string
  default     = "gruber-ga-server-prod"
}

variable "region" {
  description = "GCP region for regional resources."
  type        = string
  default     = "europe-west3"
}

variable "zone" {
  description = "GCP zone for the VM and data disk."
  type        = string
  default     = "europe-west3-a"
}

variable "manage_project_services" {
  description = "Enable required Google APIs. Keep false when APIs are managed manually."
  type        = bool
  default     = false
}

variable "create_network" {
  description = "Create a VPC. False references existing_network_name."
  type        = bool
  default     = false
}

variable "network_name" {
  description = "Name of the VPC created when create_network is true."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_network_name" {
  description = "Existing VPC name used when create_network is false."
  type        = string
  default     = "ga-server-vpc"
}

variable "create_subnetwork" {
  description = "Create a subnet. False references existing_subnetwork_name."
  type        = bool
  default     = false
}

variable "subnetwork_name" {
  description = "Name of the subnet created when create_subnetwork is true."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_subnetwork_name" {
  description = "Existing subnet name used when create_subnetwork is false."
  type        = string
  default     = null
  nullable    = true
}

variable "subnet_cidr" {
  description = "CIDR used only when Terraform creates the subnet."
  type        = string
  default     = null
  nullable    = true
}

variable "create_static_ip" {
  description = "Create a regional external IPv4 address. False uses the supplied existing address."
  type        = bool
  default     = false
}

variable "static_ip_name" {
  description = "Name of the static address created when create_static_ip is true."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_static_ip_name" {
  description = "Existing static address name used for documentation and outputs."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_static_ip_address" {
  description = "Existing external IPv4 address attached when create_static_ip is false."
  type        = string
  default     = null
  nullable    = true
}

variable "create_firewall_rules" {
  description = "Create the narrowly scoped public and IAP ingress rules."
  type        = bool
  default     = false
}

variable "public_firewall_rule_name" {
  description = "Explicit name for the public web and MQTT-TLS firewall rule."
  type        = string
  default     = null
  nullable    = true
}

variable "iap_firewall_rule_name" {
  description = "Explicit name for the IAP-only SSH firewall rule."
  type        = string
  default     = null
  nullable    = true
}

variable "create_service_account" {
  description = "Create the runtime service account. False uses existing_service_account_email."
  type        = bool
  default     = false
}

variable "service_account_id" {
  description = "Account ID for a newly created runtime service account."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_service_account_email" {
  description = "Existing runtime service account email."
  type        = string
  default     = "ga-server-vm@gruber-ga-server-prod.iam.gserviceaccount.com"
}

variable "manage_runtime_iam" {
  description = "Grant logging, monitoring, exact-secret and optional bucket access to the selected service account."
  type        = bool
  default     = false
}

variable "manage_admin_iam" {
  description = "Grant IAP tunnel and OS Admin Login roles to admin_members."
  type        = bool
  default     = false
}

variable "admin_members" {
  description = "IAM members for IAP and OS Admin Login, for example [\"user:name@example.com\"]."
  type        = set(string)
  default     = []
}

variable "create_mqtt_secret" {
  description = "Create Secret Manager metadata only; no secret value enters Terraform state."
  type        = bool
  default     = false
}

variable "mqtt_secret_name" {
  description = "Name of the Secret Manager secret created when create_mqtt_secret is true."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_mqtt_secret_name" {
  description = "Existing Secret Manager secret name. Leave null to require a manually provisioned file."
  type        = string
  default     = null
  nullable    = true
}

variable "enable_gcs_backups" {
  description = "Enable GCS bucket references and runtime IAM for application backups."
  type        = bool
  default     = false
}

variable "create_backup_bucket" {
  description = "Create the GCS backup bucket. Requires enable_gcs_backups."
  type        = bool
  default     = false
}

variable "backup_bucket_name" {
  description = "Explicit globally unique name for a newly created backup bucket."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_backup_bucket_name" {
  description = "Existing GCS backup bucket name."
  type        = string
  default     = null
  nullable    = true
}

variable "backup_retention_days" {
  description = "Object and snapshot retention in days."
  type        = number
  default     = 14

  validation {
    condition     = var.backup_retention_days >= 1
    error_message = "backup_retention_days must be at least 1."
  }
}

variable "create_data_disk" {
  description = "Create a persistent data disk. False references existing_data_disk_name."
  type        = bool
  default     = false
}

variable "data_disk_name" {
  description = "Name of the data disk created when create_data_disk is true."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_data_disk_name" {
  description = "Existing persistent data disk name."
  type        = string
  default     = null
  nullable    = true
}

variable "data_disk_size_gb" {
  description = "Size in GiB for a newly created persistent data disk."
  type        = number
  default     = 20
}

variable "data_disk_device_name" {
  description = "Stable guest device name used for the attached data disk."
  type        = string
  default     = "ga-server-data"
}

variable "allow_data_disk_format" {
  description = "Explicitly allow bootstrap to format an unformatted data disk. Keep false for existing disks."
  type        = bool
  default     = false
}

variable "create_snapshot_policy" {
  description = "Create and attach a daily snapshot policy to the selected data disk."
  type        = bool
  default     = false
}

variable "snapshot_policy_name" {
  description = "Explicit name for a newly created snapshot policy."
  type        = string
  default     = null
  nullable    = true
}

variable "create_instance" {
  description = "Create or manage the VM. Set true before importing an existing VM into google_compute_instance.server[0]."
  type        = bool
  default     = false
}

variable "instance_name" {
  description = "Explicit Compute Engine instance name."
  type        = string
  default     = null
  nullable    = true
}

variable "existing_instance_name" {
  description = "Existing unmanaged VM name for documentation and outputs."
  type        = string
  default     = null
  nullable    = true
}

variable "machine_type" {
  description = "Compute Engine machine type for a Terraform-managed VM."
  type        = string
  default     = "e2-small"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size in GiB for a Terraform-managed VM."
  type        = number
  default     = 20
}

variable "internal_ip" {
  description = "Optional fixed internal IPv4 address. Null lets GCP allocate one."
  type        = string
  default     = null
  nullable    = true
}

variable "deletion_protection" {
  description = "Protect a Terraform-managed VM against accidental deletion."
  type        = bool
  default     = true
}

variable "deployment_source_base_url" {
  description = "Raw repository base URL used to fetch only deploy/gcp/bootstrap.sh and deploy/production files."
  type        = string
  default     = "https://raw.githubusercontent.com/henrigruber-ai/GA-Server"
}

variable "deployment_source_ref" {
  description = "Immutable release tag or full commit SHA for deployment files. main is allowed only for controlled testing."
  type        = string
  default     = "v0.1.2"

  validation {
    condition = (
      can(regex("^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$", var.deployment_source_ref)) &&
      !strcontains(var.deployment_source_ref, "..")
    )
    error_message = "deployment_source_ref must be a safe Git ref without '..'."
  }
}

variable "image_tag" {
  description = "GA-Server GHCR tag: latest, main, sha-<commit> or a semantic version such as 0.1.2."
  type        = string
  default     = "0.1.2"

  validation {
    condition = can(regex(
      "^(latest|main|sha-[0-9a-f]{7,40}|[0-9]+\\.[0-9]+\\.[0-9]+)$",
      var.image_tag,
    ))
    error_message = "image_tag must be latest, main, sha-<7-40 lowercase hex characters>, or x.y.z."
  }
}

variable "public_base_url" {
  description = "Public HTTPS origin, without a path, written only to a new non-secret .env."
  type        = string
  default     = null
  nullable    = true
}

variable "mqtt_public_host" {
  description = "Public MQTT DNS name written only to a new non-secret .env."
  type        = string
  default     = null
  nullable    = true
}

variable "acme_email" {
  description = "Non-secret ACME contact email written only to a new .env."
  type        = string
  default     = null
  nullable    = true
}
