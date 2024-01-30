terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    hcp = {
      source  = "hashicorp/hcp"
      version = "~> 0.82"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Application = "HCP Packer"
      Automation  = "terraform"
      Environment = "demo"
      Owner       = "dan.barr"
      HCPOrg      = data.hcp_organization.current.name
      HCPProject  = data.hcp_project.current.name
    }
  }
}

provider "hcp" {}

data "hcp_organization" "current" {}

data "hcp_project" "current" {}

locals {
  hcp_org_name     = data.hcp_organization.current.name
  hcp_project_name = data.hcp_project.current.name
  base_name        = "hcp-packer-webhook-handler_${local.hcp_org_name}"
}

resource "hcp_service_principal" "webhook" {
  name   = "hcp-packer-webhook-handler"
  parent = data.hcp_project.current.resource_name
}

resource "hcp_project_iam_binding" "webhook" {
  project_id   = data.hcp_project.current.resource_id
  principal_id = hcp_service_principal.webhook.resource_id
  role         = "roles/viewer"
}

resource "hcp_service_principal_key" "webhook" {
  service_principal = hcp_service_principal.webhook.resource_name
}

resource "aws_secretsmanager_secret" "hcp_credential" {
  name                    = "${local.base_name}-hcp-credential"
  description             = "HCP credentials for webhook handler. Org: ${local.hcp_org_name}, project: ${local.hcp_project_name}."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "hcp_credential" {
  secret_id = aws_secretsmanager_secret.hcp_credential.id

  secret_string = jsonencode({
    HCP_CLIENT_ID     = hcp_service_principal_key.webhook.client_id
    HCP_CLIENT_SECRET = hcp_service_principal_key.webhook.client_secret
  })
}

resource "random_password" "hmac_token" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "hmac_token" {
  name                    = "${local.base_name}-hmac-token"
  description             = "HMAC token for webhook validation. Org: ${local.hcp_org_name}, project: ${local.hcp_project_name}."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "hmac_token" {
  secret_id     = aws_secretsmanager_secret.hmac_token.id
  secret_string = random_password.hmac_token.result
}

resource "hcp_notifications_webhook" "aws" {
  name        = var.hcp_webhook_name
  description = var.hcp_webhook_description
  enabled     = true

  config = {
    hmac_key = aws_secretsmanager_secret_version.hmac_token.secret_string
    url      = "${aws_api_gateway_stage.webhook.invoke_url}/${aws_api_gateway_resource.webhook.path_part}"
  }

  subscriptions = [
    {
      events = [
        {
          actions = ["complete", "delete", "restore", "revoke"]
          source  = "hashicorp.packer.version"
        },
      ]
    },
  ]
}
