# File: deploy/gcp/terraform/versions.tf
# Version: 0.1.2
# Date: 2026-08-04
# Purpose: Pins the Terraform and Google provider requirements for GA-Server infrastructure.

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
}
