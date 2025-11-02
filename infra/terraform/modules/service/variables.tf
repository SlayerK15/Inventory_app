variable "name" {
  type        = string
  description = "Service name"
}

variable "image" {
  type        = string
  description = "Container image"
}

variable "cpu" {
  type        = number
  description = "Task CPU units"
}

variable "memory" {
  type        = number
  description = "Task memory"
}

variable "container_port" {
  type        = number
  description = "Container port"
  default     = 8000
}

variable "desired_count" {
  type        = number
  description = "Desired service tasks"
  default     = 1
}

variable "assign_public_ip" {
  type        = bool
  default     = false
}

variable "cluster_arn" {
  type        = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "log_group_name" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "target_group_arn" {
  type = string
}

variable "lb_listener_dependency" {
  description = "Explicit dependency to ensure listener exists"
  type        = any
}
