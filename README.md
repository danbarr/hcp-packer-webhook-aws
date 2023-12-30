# HCP Packer webhook handler for AWS

Implements a handler for HCP Packer webhook events for AWS AMIs, using an API Gateway and Lambda function.

Currently handles the following HCP Packer events:

- Completed iteration: adds tags to the AMI(s) with HCP Packer metadata
- Revoked iteration: deprecates the AMI(s) and adds the revocation reason as a tag
- Restored iteration: cancels the AMI deprecation and removes the tags added by the revoked handler
- Deleted iteration: deregisters the AMI(s) and deletes the associated snapshots

## Prerequisites

- An HCP service account (organization or project level) to bootstrap the configuration ("Admin" role is required to create a new project-level service account for the handler to use).
- A key for the above service account set in `HCP_CLIENT_ID` and `HCP_CLIENT_SECRET` environment variables to authenticate the `hcp` provider. If a project-level service account is used, `HCP_PROJECT_ID` is also required. Refer to the [Authenticate with HCP](https://registry.terraform.io/providers/hashicorp/hcp/latest/docs/guides/auth) guide in the provider docs.

## Usage

This configuration will create everything except the webhook in HCP. Webhooks are not yet suppored by the HCP provider.

1. Apply this Terraform configuration to create the webhook handler resources.
2. Obtain the generated HMAC token from AWS Secrets Manager.
3. Create a webhook in your HCP project settings, specifying the URL (output from this confic) and HMAC token.
4. Enable the following registry events:
   1. Completed iteration
   2. Revoked iteration
   3. Restored iteration
   4. Deleted iteration

<!-- BEGIN_TF_DOCS -->
## Providers

| Name | Version |
|------|---------|
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | ~> 2.4 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.0 |
| <a name="requirement_hcp"></a> [hcp](#requirement\_hcp) | ~> 0.79 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.6 |

## Modules

No modules.

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_log_retention_days"></a> [log\_retention\_days](#input\_log\_retention\_days) | Number of days to retain CloudWatch logs. | `number` | `14` | no |
| <a name="input_region"></a> [region](#input\_region) | The AWS region to use. | `string` | n/a | yes |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_webhook_url"></a> [webhook\_url](#output\_webhook\_url) | URL of the webhook handler. |

## Resources

| Name | Type |
|------|------|
| [aws_api_gateway_deployment.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_deployment) | resource |
| [aws_api_gateway_integration.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_integration) | resource |
| [aws_api_gateway_method.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_method) | resource |
| [aws_api_gateway_method_settings.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_method_settings) | resource |
| [aws_api_gateway_resource.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_resource) | resource |
| [aws_api_gateway_rest_api.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_rest_api) | resource |
| [aws_api_gateway_stage.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_stage) | resource |
| [aws_cloudwatch_log_group.webhook_api_gateway](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_cloudwatch_log_group.webhook_function](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_iam_role.lambda_execution_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_lambda_function.webhook](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_permission.apigw_lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_secretsmanager_secret.hcp_credential](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret.hmac_token](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret_version.hcp_credential](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_secretsmanager_secret_version.hmac_token](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [hcp_project_iam_binding.webhook](https://registry.terraform.io/providers/hashicorp/hcp/latest/docs/resources/project_iam_binding) | resource |
| [hcp_service_principal.webhook](https://registry.terraform.io/providers/hashicorp/hcp/latest/docs/resources/service_principal) | resource |
| [hcp_service_principal_key.webhook](https://registry.terraform.io/providers/hashicorp/hcp/latest/docs/resources/service_principal_key) | resource |
| [random_password.hmac_token](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/password) | resource |
| [archive_file.webhook_lambda](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |
| [aws_iam_policy_document.lambda_assume_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.lambda_get_secrets](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_iam_policy_document.lambda_manage_ami](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [hcp_organization.current](https://registry.terraform.io/providers/hashicorp/hcp/latest/docs/data-sources/organization) | data source |
| [hcp_project.current](https://registry.terraform.io/providers/hashicorp/hcp/latest/docs/data-sources/project) | data source |
<!-- END_TF_DOCS -->