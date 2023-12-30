variable "region" {
  type        = string
  description = "The AWS region to use."
}

variable "log_retention_days" {
  type        = number
  description = "Number of days to retain CloudWatch logs."
  default     = 14
}

variable "enable_api_gateway_logging" {
  type        = bool
  description = "Whether to enable API Gateway logging."
  default     = false
}

variable "api_gateway_logging_level" {
  type        = string
  description = "Log level for API Gateway execution logging."
  default     = "ERROR"
  validation {
    condition     = contains(["OFF", "ERROR", "INFO"], var.api_gateway_logging_level)
    error_message = "Invalid logging level specified."
  }
}
