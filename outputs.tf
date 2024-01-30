output "webhook_url" {
  description = "API Gateway URL of the webhook handler in AWS."
  value       = "${aws_api_gateway_stage.webhook.invoke_url}/${aws_api_gateway_resource.webhook.path_part}"
}

output "hcp_webhook_resource_name" {
  description = "API resource name of the HCP notification webhook."
  value       = hcp_notifications_webhook.aws.resource_name
}
