# File: deploy/gcp/terraform/variables.tf
# Version: 0.1.0
# Date: 2026-08-04
# Purpose: Declares the configurable values for the GA-Server GCP deployment.

variable "project_id" {
  description = "Existing GCP project ID with billing enabled."
  type        = string
}

variable "region" {
  description = "GCP region for network, address, backup bucket and snapshot policy."
  type        = string
  default     = "europe-west3"
}

variable "zone" {
  description = "GCP zone for the VM and persistent data disk."
  type        = string
  default     = "europe-west3-a"
}

variable "environment" {
  description = "Short environment label used in resource names and labels."
  type        = string
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,12}$", var.environment))
    error_message = "environment may contain only lowercase letters, numbers and hyphens and must be at most 12 characters."
  }
}

variable "instance_name" {
  description = "Compute Engine instance name."
  type        = string
  default     = "ga-server-01"
}

variable "machine_type" {
  description = "Compute Engine machine type. e2-small is sufficient for the initial four Shelly devices."
  type        = string
  default     = "e2-small"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size in GiB."
  type        = number
  default     = 20
}

variable "data_disk_size_gb" {
  description = "Persistent application data disk size in GiB."
  type        = number
  default     = 20
}

variable "subnet_cidr" {
  description = "CIDR range for the dedicated GA-Server subnet."
  type        = string
  default     = "10.130.0.0/24"
}

variable "backup_retention_days" {
  description = "Retention for GCS backups and scheduled disk snapshots."
  type        = number
  default     = 14
}

variable "backup_bucket_name" {
  description = "Globally unique GCS bucket name. Leave null to use <project-id>-ga-server-backups."
  type        = string
  default     = null
  nullable    = true
}

variable "repository_url" {
  description = "Public Git repository cloned onto the VM by the startup script."
  type        = string
  default     = "https://github.com/henrigruber-ai/GA-Server.git"
}

variable "repository_ref" {
  description = "Branch or tag checked out by the VM bootstrap. Use a signed release tag in production."
  type        = string
  default     = "main"
}

variable "admin_members" {
  description = "IAM members allowed to use IAP and OS Login, for example [\"user:name@example.com\"]."
  type        = set(string)
  default     = []
}

variable "deletion_protection" {
  description = "Protect the VM against accidental deletion after the initial setup is complete."
  type        = bool
  default     = false
}
