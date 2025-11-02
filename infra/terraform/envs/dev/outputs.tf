output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "gateway_service_name" {
  value = module.gateway_service.service_name
}

output "db_endpoint" {
  value = module.datastores.db_endpoint
}
