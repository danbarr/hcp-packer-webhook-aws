output "webhook_url" {
  description = "URL of the webhook handler."
  value       = "${aws_api_gateway_stage.webhook.invoke_url}/${aws_api_gateway_resource.webhook.path_part}"
}
