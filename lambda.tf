data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda_execution_role" {
  name                = "${local.base_name}-lambda-role"
  description         = "Execution role for the HCP Packer webhook handler Lambda function for HCP org '${local.hcp_org_name}', project '${local.hcp_project_name}'."
  assume_role_policy  = data.aws_iam_policy_document.lambda_assume_role.json
  managed_policy_arns = ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"]

  inline_policy {
    name   = "lambda-manage-ami"
    policy = data.aws_iam_policy_document.lambda_manage_ami.json
  }

  inline_policy {
    name   = "lambda-get-secrets"
    policy = data.aws_iam_policy_document.lambda_get_secrets.json
  }
}

data "aws_iam_policy_document" "lambda_manage_ami" {
  statement {
    effect = "Allow"

    actions = [
      "ec2:CreateTags",
      "ec2:DeleteTags",
      "ec2:DescribeImages",
      "ec2:*ImageDeprecation",
      "ec2:ModifyImageAttribute",
      "ec2:DeregisterImage",
      "ec2:DescribeSnapshots",
      "ec2:DeleteSnapshot",
    ]

    resources = ["*"]
  }
}

data "aws_iam_policy_document" "lambda_get_secrets" {
  statement {
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]

    resources = [
      aws_secretsmanager_secret.hmac_token.arn,
      aws_secretsmanager_secret.hcp_credential.arn,
    ]
  }
}

data "archive_file" "webhook_lambda" {
  type        = "zip"
  source_file = "${path.module}/function/lambda_function.py"
  output_path = "${path.module}/function/lambda_function.zip"
}

resource "aws_lambda_function" "webhook" {
  function_name    = local.base_name
  description      = "HCP Packer webhook handler for HCP org '${local.hcp_org_name}', project '${local.hcp_project_name}'."
  filename         = data.archive_file.webhook_lambda.output_path
  source_code_hash = data.archive_file.webhook_lambda.output_base64sha256
  role             = aws_iam_role.lambda_execution_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30

  environment {
    variables = {
      HMAC_TOKEN_ARN     = aws_secretsmanager_secret.hmac_token.arn
      HCP_CREDENTIAL_ARN = aws_secretsmanager_secret.hcp_credential.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.webhook_function]
}

resource "aws_cloudwatch_log_group" "webhook_function" {
  name              = "/aws/lambda/${local.base_name}"
  retention_in_days = var.log_retention_days
}
