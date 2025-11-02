# Inventory Platform

A full-stack inventory tracking platform composed of FastAPI microservices, a Next.js dashboard, and an Android client. The services persist data in PostgreSQL, exchange JSON payloads, and surface a gateway that unifies authentication and orchestration.

## Features

- **Account service** – user registration, password hashing, JWT-based authentication, and seeded default manager account.
- **Inventory service** – CRUD for stock items, quantity adjustments with validation, low-stock detection, and downstream log + notification fan-out.
- **Log service** – persistent audit trail with JSON metadata and JWT-aware read APIs.
- **Notifier service** – records notification requests for low-stock events.
- **Gateway** – exposes `/auth`, `/dashboard`, `/inventory`, `/logs`, and `/notifications` endpoints for web and mobile clients.
- **Web dashboard** – Next.js client with authentication flow, item creation, stock adjustments, and alert visibility.
- **Android client** – Jetpack Compose experience with in-app authentication and inventory listing.

## Quick start

Requirements:

- Docker & Docker Compose
- Make (optional for shortcuts)

Launch the full stack locally:

```bash
docker compose up --build
```

Once containers are healthy:

- Gateway: http://localhost:8080
- Web dashboard (Next.js dev server): `npm install && npm run dev` from `web/dashboard`, or access the gateway endpoints directly from the running compose stack.
- Android client: update the emulator/network configuration if needed (defaults to `http://10.0.2.2:8080`).

### Default credentials

The compose stack seeds a manager account:

| Email              | Password     | Role    |
|--------------------|--------------|---------|
| `staff@example.com` | `password123` | manager |

Use these credentials to sign in on the web dashboard or Android app.

### Environment variables

Each service reads settings from environment variables (defaults shown for local dev):

| Service   | Key                         | Description                              |
|-----------|-----------------------------|------------------------------------------|
| Account   | `DATABASE_URL`              | PostgreSQL URL (shared `inventory` DB).   |
|           | `SECRET_KEY`                | JWT signing secret.                       |
|           | `DEFAULT_ADMIN_*`           | Seeding details for the manager account.  |
| Inventory | `LOG_SERVICE_URL`           | Downstream log API base URL.              |
|           | `NOTIFIER_SERVICE_URL`      | Downstream notifier base URL.             |
|           | `SERVICE_TOKEN`             | Shared token for service-to-service auth. |
| Log       | `SERVICE_TOKEN`             | Must match the inventory/notifier token.  |
| Notifier  | `SERVICE_TOKEN`             | Must match the inventory/log token.       |
| Gateway   | `SERVICE_TOKEN`             | Propagates to downstream services.        |

The compose file sets consistent values for these variables so the services can communicate securely.

## API overview

All authenticated requests expect `Authorization: Bearer <token>` headers. Tokens are obtained via `POST /auth/login` on the gateway.

| Method | Path                         | Description                               |
|--------|------------------------------|-------------------------------------------|
| POST   | `/auth/register`             | Register a new user.                      |
| POST   | `/auth/login`                | Obtain a JWT access token.                |
| GET    | `/dashboard`                 | Aggregated user, inventory, and alerts.   |
| POST   | `/inventory`                 | Create a new inventory item.              |
| POST   | `/inventory/{id}/adjust`     | Increment or decrement stock quantity.    |
| GET    | `/logs`                      | List audit log entries.                   |
| GET    | `/notifications`             | View notification history.                |

Underlying services expose similar routes under their own hosts (see `docker-compose.yml`).

## Project structure

```
.
├── services
│   ├── account/      # FastAPI account/JWT service
│   ├── inventory/    # FastAPI inventory and alerting service
│   ├── log/          # FastAPI audit log service
│   ├── notifier/     # FastAPI notification capture service
│   └── gateway/      # BFF orchestrating the microservices
├── web/dashboard     # Next.js dashboard app
├── android/          # Jetpack Compose Android client
├── infra/terraform   # AWS infrastructure modules & envs
└── docker-compose.yml
```

## Testing & development tips

- Use `docker compose logs -f <service>` to tail container logs.
- Services use SQLModel + Alembic-free auto-migrations via `create_all`; adjust models carefully when evolving schemas.
- Update `SERVICE_TOKEN` consistently across services if you customise secrets.
- Run `npm run lint` inside `web/dashboard` and `./gradlew lint` inside `android/` for client-side checks.

## Deployment

Terraform modules under `infra/terraform` provision VPC networking, ECS services, Postgres, and supporting infrastructure. Review `docs/ARCHITECTURE.md` for a deeper dive into the target AWS topology and adapt variables per environment.
