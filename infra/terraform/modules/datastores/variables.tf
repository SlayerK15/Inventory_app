variable "name" {
  type        = string
  description = "Prefix"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "instance_class" {
  type        = string
  default     = "db.t4g.micro"
}

variable "db_name" {
  type        = string
  default     = "inventory"
}

variable "username" {
  type    = string
  default = "inventory"
}

variable "password" {
  type      = string
  sensitive = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
