resource "aws_api_gateway_rest_api" "webhook" {
  name        = local.base_name
  description = "HCP Packer webhook API for HCP org '${local.hcp_org_name}', project '${local.hcp_project_name}'."
  endpoint_configuration {
    types = ["EDGE"]
  }
}

resource "aws_api_gateway_deployment" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  depends_on  = [aws_api_gateway_integration.webhook]

  lifecycle {
    create_before_destroy = true
  }
}

locals {
  stage_name = "default"
}

resource "aws_api_gateway_stage" "webhook" {
  deployment_id = aws_api_gateway_deployment.webhook.id
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  stage_name    = local.stage_name
}

resource "aws_api_gateway_resource" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  parent_id   = aws_api_gateway_rest_api.webhook.root_resource_id
  path_part   = "handler"
}

resource "aws_api_gateway_method" "webhook" {
  rest_api_id   = aws_api_gateway_rest_api.webhook.id
  resource_id   = aws_api_gateway_resource.webhook.id
  http_method   = "POST"
  authorization = "NONE"

  request_parameters = {
    "method.request.header.X-Hcp-Webhook-Signature" = true
  }
}

resource "aws_api_gateway_method_settings" "webhook" {
  rest_api_id = aws_api_gateway_rest_api.webhook.id
  stage_name  = aws_api_gateway_stage.webhook.stage_name
  method_path = "*/*"

  settings {
    logging_level      = "INFO"
    metrics_enabled    = true
    data_trace_enabled = false
  }

  depends_on = [aws_cloudwatch_log_group.webhook_api_gateway]
}

resource "aws_cloudwatch_log_group" "webhook_api_gateway" {
  name              = "API-Gateway-Execution-Logs_${aws_api_gateway_rest_api.webhook.id}/${local.stage_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_api_gateway_integration" "webhook" {
  rest_api_id             = aws_api_gateway_rest_api.webhook.id
  resource_id             = aws_api_gateway_resource.webhook.id
  http_method             = aws_api_gateway_method.webhook.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.webhook.invoke_arn
}

resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.webhook.execution_arn}/*"
}
