# Android Client

The Android module ships a Jetpack Compose application that authenticates against the FastAPI gateway and renders inventory plus low-stock alerts.

## Capabilities

- Email/password login (`/auth/login`) with tokens stored in memory for the session.
- Retrofit-powered gateway client hitting `http://10.0.2.2:8080` by default (Android emulator localhost).
- Inventory list with live refresh support and low-stock summaries.

## Running locally

1. Start the backend stack with `docker compose up --build` from the repository root.
2. Open the project in Android Studio (Giraffe or later).
3. Sync Gradle and launch the `app` configuration on an emulator or device.

Use the default credentials from the root README (`staff@example.com` / `password123`) to sign in.

## Customisation

- Update `provideApi()` in `MainActivity.kt` if the gateway base URL changes.
- Add persistent token storage (e.g., `DataStore`) before shipping to production.
- Expand the `GatewayApi` interface with additional endpoints (create item, adjust stock) as needed.
