variable "prefix" {
  type        = string
  description = "Alarm name prefix"
}

variable "alarms" {
  description = "Map describing metric alarms"
  type = map(object({
    metric_name         = string
    namespace           = string
    statistic           = string
    period              = number
    evaluation_periods  = number
    threshold           = number
    comparison_operator = string
    description         = optional(string)
    treat_missing_data  = optional(string)
    dimensions          = optional(map(string))
  }))
  default = {}
}

variable "alarm_actions" {
  type    = list(string)
  default = []
}

variable "ok_actions" {
  type    = list(string)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
