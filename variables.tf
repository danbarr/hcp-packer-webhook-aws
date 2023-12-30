variable "region" {
  type        = string
  description = "The AWS region to use."
}

variable "log_retention_days" {
  type        = number
  description = "Number of days to retain CloudWatch logs."
  default     = 14
}
