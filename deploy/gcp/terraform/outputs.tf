# File: deploy/gcp/terraform/outputs.tf
# Version: 0.2.0
# Date: 2026-08-04
# Purpose: Exposes selected resource values without assuming unknown names.

output "resource_selection" {
  description = "New or existing resources selected by this configuration."
  value = {
    network                 = local.network_name
    subnetwork              = local.subnetwork_name
    service_account_email   = local.service_account_email
    static_ip_name          = local.static_ip_name
    data_disk_name          = local.data_disk_name
    instance_name           = local.instance_output_name
    mqtt_secret_name        = local.mqtt_secret_name
    backup_bucket_name      = var.enable_gcs_backups ? local.backup_bucket_name : null
    creates_network         = var.create_network
    creates_subnetwork      = var.create_subnetwork
    creates_service_account = var.create_service_account
    creates_static_ip       = var.create_static_ip
    creates_data_disk       = var.create_data_disk
    creates_instance        = var.create_instance
  }
}

output "public_ip" {
  description = "Selected static public IPv4 address, or null when it was not supplied."
  value       = local.static_ip_address
}

output "iap_ssh_command" {
  description = "IAP SSH command when an instance name is selected."
  value = local.instance_output_name == null ? null : (
    "gcloud compute ssh ${local.instance_output_name} --project=${var.project_id} --zone=${var.zone} --tunnel-through-iap"
  )
}

output "required_dns_records" {
  description = "Manual DNS A records; Terraform does not change DNS."
  value = (
    local.static_ip_address != null &&
    var.public_base_url != null &&
    var.mqtt_public_host != null
    ) ? {
    (trimprefix(var.public_base_url, "https://")) = local.static_ip_address
    (var.mqtt_public_host)                        = local.static_ip_address
  } : {}
}
