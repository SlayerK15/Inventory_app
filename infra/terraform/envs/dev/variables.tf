variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  default     = "dev"
}

variable "availability_zones" {
  type    = list(string)
  default = ["ap-south-1a", "ap-south-1b"]
}

variable "gateway_image" {
  type        = string
  description = "ECR image for the gateway service"
}

variable "execution_role_arn" {
  type        = string
  description = "IAM role used by ECS tasks to pull images"
}

variable "task_role_arn" {
  type        = string
  description = "IAM role assumed by the gateway task"
}

variable "db_username" {
  type    = string
  default = "inventory"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "alarm_topic_arns" {
  type    = list(string)
  default = []
}
