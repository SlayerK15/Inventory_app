# Inventory Platform Architecture

The platform is a microservices-based inventory tracker with persistent storage, gateway aggregation, and multi-channel clients. Every component in this repository is runnable end-to-end via Docker Compose and is designed to deploy to AWS ECS Fargate through the provided Terraform modules.

## Microservices

| Service   | Responsibility                                                     | Language | Port |
|-----------|-------------------------------------------------------------------|----------|------|
| Gateway   | Authenticates requests, orchestrates downstream fan-out, aggregates dashboards | Python (FastAPI) | 8000 |
| Account   | Manages users, hashed credentials, roles, and JWT issuance         | Python (FastAPI) | 8000 |
| Inventory | Stores items, enforces stock adjustments, triggers logs & alerts   | Python (FastAPI) | 8000 |
| Log       | Persists audit events with JSON metadata                           | Python (FastAPI) | 8000 |
| Notifier  | Captures notification requests for low-stock conditions            | Python (FastAPI) | 8000 |

All services share a PostgreSQL database (`inventory`) and use a common `SERVICE_TOKEN` for trusted service-to-service calls.

## Data flow

1. Clients authenticate through the gateway (`/auth/login`). The gateway proxies requests to the account service which returns a signed JWT.
2. Authenticated requests include `Authorization: Bearer <token>` headers. The gateway validates/forwards tokens to downstream services.
3. Inventory mutations (`POST /inventory`, `/inventory/{id}/adjust`) call the inventory service. Successful adjustments write audit entries through the log service and trigger notifier requests when quantities fall below reorder points.
4. Low-stock notifications are stored in the notifier service and surfaced through `/notifications`.

## Persistence

- **PostgreSQL** (via Docker Compose `postgres` service) stores all entities. SQLModel automatically creates tables for:
  - `account_user`
  - `inventoryitem`
  - `auditlog`
  - `notificationrequest`
- **JWT secrets** (`SECRET_KEY`) and shared `SERVICE_TOKEN` values are configured through environment variables. Update these for production deployments.

## Clients

- **Web dashboard (`web/dashboard`)** – Next.js App Router client with client-side login, inventory creation, stock adjustments, and low-stock alert visibility. Uses the gateway REST API directly.
- **Android app (`android/`)** – Jetpack Compose UI that authenticates against the gateway and renders inventory/alert data using Retrofit.

## Infrastructure & deployment

Terraform modules under `infra/terraform` provision:

- Networking (VPC, subnets, security groups)
- ECS clusters and task definitions for each service
- RDS PostgreSQL instance
- Load balancing (ALB) and service discovery
- CloudWatch-based observability scaffolding

The `dev` environment (`infra/terraform/envs/dev`) demonstrates how to stitch modules together. Update remote state configuration and AWS account details before running `terraform apply`.

CI/CD workflows in `.github/workflows` offer a baseline for building images, running tests, and applying Terraform via GitHub Actions and OpenID Connect.

## Local development tips

- `docker compose up --build` starts the entire stack with seeded credentials.
- `docker compose logs -f <service>` tail logs for debugging.
- Services auto-migrate schemas on startup. For breaking changes, manage migrations manually before deploying.
- Rotate `SECRET_KEY` and `SERVICE_TOKEN` in lockstep across services.
