variable "name" {
  description = "ECS Cluster name"
  type        = string
}

variable "enable_container_insights" {
  description = "Toggle for CloudWatch Container Insights"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Retention for CloudWatch Logs"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
