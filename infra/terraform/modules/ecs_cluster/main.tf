resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/ecs/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.this.name
}
