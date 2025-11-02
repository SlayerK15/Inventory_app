# Inventory Tracker — Microservices AWS Architecture & Scaffold

## 0) Goals & Non‑Goals

* **Goals:** Android app + Web dashboard backed by microservices; accounts, inventory, audit logs; AWS deploy via **ECS Fargate** or **Serverless (API Gateway + Lambda)**; IaC with **Terraform**; CI/CD with GitHub Actions; observability & security baked‑in.
* **Non‑Goals:** Full feature parity with large ERPs, complex procurement flows, payments.

---

## 1) High‑Level Architecture

```
 Android App (Kotlin)         Web Dashboard (Next.js)
         |                             |
         | HTTPS (JWT via Cognito)     |  
         |                             |
                   ┌──────── API Gateway / ALB ────────┐
                   │                                    │
            ┌──────▼──────┐   ┌─────────────▼──────────┐   ┌─────────────▼──────────┐
            │  Gateway    │   │  Inventory Service     │   │   Account Service       │
            │  (BFF)      │   │  (FastAPI)             │   │   (FastAPI)             │
            └────▲────────┘   └──────────▲─────────────┘   └──────────▲─────────────┘
                 │                       │                             │
                 │                       │                             │
            ┌────┴────────┐         ┌────┴────────┐                ┌───┴────────┐
            │  Log/Audit  │◄───────▶│  Event Bus  │◄───────────────┤  Notifier  │
            │  Service    │  emits  │(EventBridge)│  fan‑out        │(SES/SNS)   │
            └────▲────────┘         └────▲────────┘                └───▲────────┘
                 │                       │                             │
     ┌───────────┴──────────┐      ┌─────┴─────┐               ┌───────┴───────┐
     │ RDS Postgres (core)  │      │ DynamoDB  │               │ S3 (images)   │
     │  accounts, inventory │      │ audit log │               │ & exports     │
     └──────────────────────┘      └───────────┘               └───────────────┘

 Observability: CloudWatch Logs, X-Ray/OTel, OpenSearch (optional); Metrics/Alarms via CloudWatch; Traces via OTel Collector.
 Security: Cognito (AuthN), IAM (AuthZ), WAF, Secrets Manager, KMS, SSM.
```

**Choice of styles:**

* **Auth:** Amazon Cognito (User Pool + Hosted UI/Custom UI). Account Service stores profile/tenancy metadata.
* **Transport:** REST JSON (gRPC optional internal). Async events via EventBridge.
* **DB:** Postgres on RDS for transactional entities; DynamoDB for immutable audit log; S3 for images/attachments; optional OpenSearch for log search.

---

## 2) Services & Responsibilities

1. **Gateway (BFF)**

   * Validates JWT (Cognito), rate limiting (WAF), request shaping for mobile/web.
   * Aggregates responses from downstream services.
2. **Account Service**

   * User profile (name, phone), org/tenant, roles, permissions mapping to Cognito groups/claims.
   * Service‑to‑service auth via IAM roles.
3. **Inventory Service**

   * Items (SKU), stock levels, locations, transactions (in/out/transfer), batches, low‑stock alerts.
   * Emits domain events (ItemCreated, StockAdjusted, LowStockAlert).
4. **Log/Audit Service**

   * Write‑once audit trails to DynamoDB; S3 archival; produces analytic exports.
5. **Notifier Service (optional)**

   * Consumes events; sends emails (SES) / push (FCM) / SMS (SNS).

---

## 3) Data Model (v1)

**Postgres (RDS)**

* `tenants(id, name, plan, created_at)`
* `users(id, tenant_id, cognito_sub, email, phone, role, created_at)`
* `locations(id, tenant_id, name)`
* `items(id, tenant_id, sku, name, description, unit, image_key)`
* `stock(id, tenant_id, item_id, location_id, qty)`
* `transactions(id, tenant_id, item_id, type, qty, ref, location_id, created_by, created_at)`

  * `type ∈ {IN, OUT, TRANSFER}`

**DynamoDB (Audit)**

* PK: `tenant_id#entity#entity_id`, SK: `timestamp#event_type`
* Attributes: `actor`, `ip`, `changes`, `user_agent`, `correlation_id`

**S3**

* Bucket `inv-media-<env>` for item images, CSV exports. Encrypted (SSE-S3/KMS), presigned upload from clients.

**Event Schemas (EventBridge)**

```json
{
  "source": "inventory.service",
  "detail-type": "StockAdjusted",
  "detail": {
    "tenant_id": "t_123",
    "item_id": "i_456",
    "delta": -3,
    "new_qty": 7,
    "location_id": "loc_1",
    "actor": "u_789",
    "correlation_id": "..."
  }
}
```

---

## 4) API (sample)

**Auth:** Cognito JWT in `Authorization: Bearer <token>`

**Inventory**

* `POST /items` {sku, name, ...}
* `GET /items?search=&page=1`
* `POST /stock/adjust` {item_id, qty, type, location_id}
* `GET /stock/:item_id/levels`
* `GET /transactions?from=&to=&type=`

**Account**

* `GET /me` -> profile + role claims
* `PATCH /me` -> update name/phone
* `GET /tenants/current` -> tenant context

**Audit**

* `GET /audit?entity=item&id=...` (paginated)

---

## 5) Repos & Local Dev

**Monorepo (suggested)**

```
inventory-tracker/
  apps/
    web/                # Next.js 15 (App Router, RSC)
    android/            # Kotlin, MVVM, Retrofit, Room (offline cache)
    otel-collector/     # OpenTelemetry Collector config
  services/
    gateway/
    account/
    inventory/
    audit/
    notifier/
  packages/
    ts-config/
    python-common/      # pydantic models, logging, tracing
  infra/
    terraform/
      envs/
        dev/
        prod/
      modules/
        vpc/
        rds/
        ecr/
        ecs-service/
        alb/
        cognito/
        dynamodb/
        s3/
        eventbridge/
        opentelemetry/
      serverless-alt/   # API GW + Lambda modules
  .github/
    workflows/
  docker-compose.yml
```

**docker-compose (dev) excerpt**

```yaml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
    ports: ["5432:5432"]
  dynamodb:
    image: amazon/dynamodb-local
    ports: ["8000:8000"]
  localstack:
    image: localstack/localstack
    environment:
      SERVICES: s3,sns,ses,sqs,sts,iam
    ports: ["4566:4566"]
  inventory:
    build: ./services/inventory
    env_file: services/inventory/.env.dev
    ports: ["8081:8080"]
    depends_on: [db]
```

---

## 6) Service Template (FastAPI)

**`services/inventory/app/main.py`**

```python
from fastapi import FastAPI, Depends
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class ItemIn(BaseModel):
    sku: str
    name: str

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/items")
async def create_item(item: ItemIn):
    # write to Postgres (sqlalchemy) + emit EventBridge event
    return {"id": "i_123", **item.model_dump()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Dockerfile (Python)**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8080
CMD ["python","-m","app.main"]
```

**requirements.txt**

```
fastapi==0.115.*
uvicorn[standard]==0.30.*
sqlalchemy==2.*
psycopg[binary]==3.*
boto3==1.*
opentelemetry-sdk==1.*
opentelemetry-instrumentation-fastapi==0.*
```

---

## 7) AWS — ECS Fargate (Primary Option)

**Core Components**

* **ECR** for images
* **ECS Fargate** for services (gateway, account, inventory, audit, notifier)
* **ALB** -> Gateway; Internal NLB for service‑to‑service (optional Service Connect)
* **RDS Postgres** (Multi‑AZ in prod)
* **DynamoDB** for audit
* **S3** (images, exports) with presigned upload
* **EventBridge** for async events
* **Cognito** for auth
* **CloudWatch** logs + metrics; X‑Ray or OTel → AWS X-Ray / OpenSearch
* **WAF** on ALB/API
* **Secrets Manager + SSM** for secrets/params

**Terraform module sketch (ECS service)**

```hcl
module "inventory_service" {
  source              = "./modules/ecs-service"
  name                = "inventory"
  cpu                 = 512
  memory              = 1024
  desired_count       = 2
  container_port      = 8080
  image               = var.inventory_image
  env = {
    DATABASE_URL = module.rds.database_url
    DYNAMODB_AUDIT_TABLE = aws_dynamodb_table.audit.name
  }
  task_execution_role_policies = [
    aws_iam_policy.ssm_read.arn,
    aws_iam_policy.xray_write.arn
  ]
  task_role_policies = [
    aws_iam_policy.dynamodb_audit_rw.arn,
    aws_iam_policy.eventbridge_put.arn
  ]
  attach_to_alb       = false
  service_discovery   = true
}
```

**Networking**

* VPC (3 AZ), public subnets (ALB), private subnets (ECS + RDS), NAT Gateway (costly; consider 1 NAT in dev). SGs least‑privilege.

---

## 8) AWS — Serverless Alternative

* **API Gateway HTTP** → **Lambda** functions per endpoint (inventory, account, audit)
* **Aurora Serverless v2 (Postgres)** or **RDS Proxy + Lambda** (cold start tuned)
* **DynamoDB** audit, **EventBridge** events, **S3** media
* **Cognito** auth, **WAF** on API GW
* **IaC:** Terraform modules under `infra/terraform/serverless-alt` with `aws_lambda_function`, `aws_apigatewayv2_*`, `aws_iam_role` etc.

**Pros:** pay‑per‑use, simpler Ops. **Cons:** DB concurrency limits, cold starts (mitigated), local parity trickier.

---

## 9) CI/CD (GitHub Actions)

* **Pipelines:**

  * `ci.yml` for lint/test; matrix per service.
  * `deploy.yml` build & push Docker → ECR, then `terraform apply` with OIDC.

**deploy.yml snippet**

```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ap-south-1
      - name: Build & Push images
        run: |
          ./scripts/build_push.sh services/inventory inventory:$(git rev-parse --short HEAD)
      - name: Terraform Init/Plan/Apply
        run: |
          cd infra/terraform/envs/dev
          terraform init -upgrade
          terraform apply -auto-approve
```

---

## 10) Observability & Logging

* **Structured logs** (JSON) → CloudWatch; retention 30–90d.
* **Tracing:** OpenTelemetry SDK; OTel Collector sidecar/daemon → X‑Ray.
* **Metrics & Alarms:** 5xx rate, latency P95, task CPU/mem, RDS CPU/conn, DynamoDB throttles.
* **Audit:** DynamoDB TTL + S3 Glacier archival via Data Lifecycle.

---

## 11) Security & Multi‑Tenancy

* JWT from Cognito; **tenant_id** in custom claim; enforce RLS at app layer.
* Separate DB schema per tenant (optional) or shared schema with tenant_id FK (default).
* WAF: rate limits + managed rules; ALB → TLS 1.2; ACM certs.
* Least‑privilege IAM; Secrets in Secrets Manager; CMK for RDS + S3.

---

## 12) Android & Web App Notes

**Android (Kotlin)**

* MVVM + Repository; Retrofit2 + OkHttp; Room for offline cache; WorkManager for sync; FCM for pushes.

**Web Dashboard (Next.js)**

* Auth via `next-auth` + Cognito; TanStack Query; Server Actions; charts with Recharts; file uploads via presigned URLs to S3.

---

## 13) Incremental Delivery Plan (4 sprints)

1. **Sprint 1:** Auth (Cognito) + Account Service + basic Next.js dashboard scaffold + Android login; ECS Dev env.
2. **Sprint 2:** Inventory CRUD + Stock Adjust + Postgres + EventBridge + Audit writes to DynamoDB.
3. **Sprint 3:** Low‑stock alerts + Notifier (SES/FCM) + CSV export to S3 + Role/permissions.
4. **Sprint 4:** Observability, WAF, cost guardrails, prod rollout.

---

## 14) Rough Monthly Cost (ap-south-1, small dev)

* ECS Fargate (5 services x 0.25 vCPU/0.5GB, 1 task each ~ dev): ~$45–60
* RDS t4g.micro Multi‑AZ (prod) or single‑AZ (dev): ~$20–90
* DynamoDB (on‑demand low): ~$5–10
* ALB + data: ~$20–30
* S3 + requests: ~$3–10
* Cognito MAU small: ~$5–15
* CloudWatch logs/metrics: ~$5–20
  **Total dev ballpark:** **$100–200/mo**; prod scales accordingly.

---

## 15) Next Steps

1. Confirm ECS vs Serverless (default: ECS Fargate).
2. Generate repo with scaffolds above; wire CI/CD and Terraform backend (S3 + DynamoDB lock).
3. Stand up **dev** environment, then ship Sprint 1.

---

## 16) TODO Backlog

* RBAC policy matrix (viewer, staff, manager, admin)
* Idempotency keys for writes
* Bulk import (CSV → S3 → Lambda → Inventory Service)
* Soft‑delete + recovery window for items
* E2E tests (Playwright) & contract tests (Pact)
