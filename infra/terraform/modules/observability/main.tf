resource "aws_cloudwatch_metric_alarm" "service_alarms" {
  for_each = var.alarms

  alarm_name          = "${var.prefix}-${each.key}"
  comparison_operator = each.value.comparison_operator
  evaluation_periods  = each.value.evaluation_periods
  metric_name         = each.value.metric_name
  namespace           = each.value.namespace
  period              = each.value.period
  statistic           = each.value.statistic
  threshold           = each.value.threshold
  alarm_description   = lookup(each.value, "description", "")
  treat_missing_data  = lookup(each.value, "treat_missing_data", "notBreaching")

  dimensions = lookup(each.value, "dimensions", null)

  alarm_actions = var.alarm_actions
  ok_actions    = var.ok_actions

  tags = var.tags
}
