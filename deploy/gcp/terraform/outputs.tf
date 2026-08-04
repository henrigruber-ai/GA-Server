# File: deploy/gcp/terraform/outputs.tf
# Version: 0.1.0
# Date: 2026-08-04
# Purpose: Exposes deployment values needed for DNS, SSH and operations.

output "instance_name" {
  description = "Compute Engine instance name."
  value       = google_compute_instance.server.name
}

output "public_ip" {
  description = "Static public IPv4 address for both A records."
  value       = google_compute_address.public.address
}

output "internal_ip" {
  description = "Stable internal VM address."
  value       = google_compute_instance.server.network_interface[0].network_ip
}

output "backup_bucket" {
  description = "GCS bucket receiving application backups."
  value       = google_storage_bucket.backups.name
}

output "mqtt_secret_name" {
  description = "Secret Manager secret that stores the internal MQTT password."
  value       = google_secret_manager_secret.mqtt_password.secret_id
}

output "iap_ssh_command" {
  description = "IAP SSH command for the VM."
  value       = "gcloud compute ssh ${google_compute_instance.server.name} --project=${var.project_id} --zone=${var.zone} --tunnel-through-iap"
}

output "required_dns_records" {
  description = "DNS records that must point to the reserved public IP."
  value = {
    "strom.gruber-automation.de"      = google_compute_address.public.address
    "mqtt.strom.gruber-automation.de" = google_compute_address.public.address
  }
}
