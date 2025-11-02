import importlib
import sys
from typing import Tuple

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlmodel import SQLModel


@pytest.fixture
def account_client(tmp_path, monkeypatch) -> Tuple[TestClient, object]:
    db_path = tmp_path / "account.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DEFAULT_ADMIN_EMAIL", "")
    module_name = "services.account.app.main"
    SQLModel.metadata.clear()
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    module.pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    with TestClient(module.app) as client:
        yield client, module


def register_user(client: TestClient, email: str, password: str, role: str = "viewer") -> None:
    payload = {
        "email": email,
        "password": password,
        "full_name": "Test User",
        "role": role,
        "tenant_id": "test-tenant",
    }
    response = client.post("/register", json=payload)
    assert response.status_code == 201, response.text


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "access_token" in body
    return body["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_and_profile(account_client: Tuple[TestClient, object]) -> None:
    client, _module = account_client
    register_user(client, "manager@example.com", "password123", role="manager")
    token = login(client, "manager@example.com", "password123")

    profile = client.get("/users/me", headers=auth_header(token))
    assert profile.status_code == 200
    body = profile.json()
    assert body["email"] == "manager@example.com"
    assert body["role"] == "manager"


def test_manager_can_list_users(account_client: Tuple[TestClient, object]) -> None:
    client, _module = account_client
    register_user(client, "manager@example.com", "password123", role="manager")
    register_user(client, "viewer@example.com", "password123", role="viewer")

    token = login(client, "manager@example.com", "password123")
    response = client.get("/users", headers=auth_header(token))
    assert response.status_code == 200
    emails = {user["email"] for user in response.json()}
    assert {"manager@example.com", "viewer@example.com"}.issubset(emails)


def test_viewer_cannot_list_users(account_client: Tuple[TestClient, object]) -> None:
    client, _module = account_client
    register_user(client, "manager@example.com", "password123", role="manager")
    register_user(client, "viewer@example.com", "password123", role="viewer")

    viewer_token = login(client, "viewer@example.com", "password123")
    response = client.get("/users", headers=auth_header(viewer_token))
    assert response.status_code == 403
