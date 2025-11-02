resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db-subnets"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.name}-postgres"
  engine                  = "postgres"
  engine_version          = "15.4"
  instance_class          = var.instance_class
  allocated_storage       = 20
  db_name                 = var.db_name
  username                = var.username
  password                = var.password
  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = var.security_group_ids
  publicly_accessible     = false
  skip_final_snapshot     = true
  backup_retention_period = 7
  tags                    = var.tags
}

resource "aws_dynamodb_table" "audit" {
  name           = "${var.name}-audit"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "pk"
  range_key      = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  tags = var.tags
}

resource "aws_s3_bucket" "media" {
  bucket = "${var.name}-${var.environment}-media"
  tags   = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

output "db_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "audit_table_name" {
  value = aws_dynamodb_table.audit.name
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}
