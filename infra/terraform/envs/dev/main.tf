terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "<replace-with-shared-terraform-state>"
    key            = "inventory-app/dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "<replace-with-shared-lock-table>"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  tags = {
    Project     = "inventory-app"
    Environment = var.environment
  }
}

module "network" {
  source             = "../../modules/network"
  name               = "inventory-app"
  cidr_block         = "10.0.0.0/16"
  availability_zones = var.availability_zones
  tags               = local.tags
}

module "ecs" {
  source                    = "../../modules/ecs_cluster"
  name                      = "inventory-app"
  tags                      = local.tags
  enable_container_insights = true
  log_retention_days        = 14
}

resource "aws_security_group" "ecs_tasks" {
  name        = "inventory-app-ecs-tasks"
  description = "Allow inbound traffic from ALB"
  vpc_id      = module.network.vpc_id

  ingress {
    protocol        = "tcp"
    from_port       = 8000
    to_port         = 8000
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_security_group" "alb" {
  name        = "inventory-app-alb"
  description = "Allow public HTTP access"
  vpc_id      = module.network.vpc_id

  ingress {
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_lb" "this" {
  name               = "inventory-app-alb"
  load_balancer_type = "application"
  subnets            = module.network.public_subnet_ids
  security_groups    = [aws_security_group.alb.id]
  tags               = local.tags
}

resource "aws_lb_target_group" "gateway" {
  name     = "inventory-gateway"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = module.network.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    path                = "/healthz"
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
}

module "datastores" {
  source             = "../../modules/datastores"
  name               = "inventory-app"
  environment        = var.environment
  subnet_ids         = module.network.private_subnet_ids
  security_group_ids = [aws_security_group.ecs_tasks.id]
  username           = var.db_username
  password           = var.db_password
  tags               = local.tags
}

module "gateway_service" {
  source                   = "../../modules/service"
  name                     = "gateway"
  image                    = var.gateway_image
  cpu                      = 256
  memory                   = 512
  cluster_arn              = module.ecs.cluster_arn
  subnet_ids               = module.network.private_subnet_ids
  security_group_ids       = [aws_security_group.ecs_tasks.id]
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn
  log_group_name           = module.ecs.log_group_name
  region                   = var.aws_region
  target_group_arn         = aws_lb_target_group.gateway.arn
  lb_listener_dependency   = aws_lb_listener.http
  environment = {
    GATEWAY_ACCOUNT_SERVICE_URL   = "http://account.service:8000"
    GATEWAY_INVENTORY_SERVICE_URL = "http://inventory.service:8000"
    GATEWAY_LOG_SERVICE_URL       = "http://log.service:8000"
  }
}

module "observability" {
  source        = "../../modules/observability"
  prefix        = "inventory-app"
  alarm_actions = var.alarm_topic_arns
  ok_actions    = var.alarm_topic_arns
  tags          = local.tags
  alarms = {
    gateway_5xx = {
      metric_name         = "HTTPCode_Target_5XX_Count"
      namespace           = "AWS/ApplicationELB"
      statistic           = "Sum"
      period              = 60
      evaluation_periods  = 1
      threshold           = 5
      comparison_operator = "GreaterThanThreshold"
      description         = "High number of gateway 5xx responses"
      dimensions = {
        LoadBalancer = aws_lb.this.arn_suffix
      }
    }
  }
}
