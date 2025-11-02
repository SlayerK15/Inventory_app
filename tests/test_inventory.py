import importlib
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel


class DummyResponse:
    status_code = 200

    @staticmethod
    def raise_for_status() -> None:
        return None


class DummyAsyncClient:
    def __init__(self, requests: List[Dict[str, Any]], *args: Any, **kwargs: Any) -> None:
        self._requests = requests

    async def __aenter__(self) -> "DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, json: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> DummyResponse:
        self._requests.append({"url": url, "json": json or {}, "headers": headers or {}})
        return DummyResponse()


@pytest.fixture
def inventory_client(tmp_path, monkeypatch) -> Tuple[TestClient, object, List[Dict[str, Any]]]:
    db_path = tmp_path / "inventory.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("LOG_SERVICE_URL", "http://log-service")
    monkeypatch.setenv("NOTIFIER_SERVICE_URL", "http://notifier-service")
    monkeypatch.setenv("SERVICE_TOKEN", "svc-token")

    module_name = "services.inventory.app.main"
    SQLModel.metadata.clear()
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    recorded_requests: List[Dict[str, Any]] = []

    def factory(*args: Any, **kwargs: Any) -> DummyAsyncClient:
        return DummyAsyncClient(recorded_requests, *args, **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)  # type: ignore[arg-type]

    with TestClient(module.app) as client:
        yield client, module, recorded_requests


def build_token(module: object, user_id: str = "1") -> str:
    payload = {"sub": user_id, "exp": datetime.utcnow() + timedelta(minutes=5)}
    return module.jwt.encode(payload, module.SECRET_KEY, algorithm=module.ALGORITHM)  # type: ignore[attr-defined]


def auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_inventory_workflow(inventory_client: Tuple[TestClient, object, List[Dict[str, Any]]]) -> None:
    client, module, requests = inventory_client
    token = build_token(module)

    create_payload = {
        "sku": "SKU-001",
        "name": "Demo Item",
        "description": "Initial stock",
        "quantity": 10,
        "location": "A1",
        "reorder_point": 5,
        "tenant_id": "test-tenant",
    }

    create_response = client.post("/items", json=create_payload, headers=auth_header(token))
    assert create_response.status_code == 201, create_response.text
    item = create_response.json()
    assert item["sku"] == "SKU-001"
    assert len(requests) == 1  # log fan-out on create
    assert requests[0]["headers"]["X-Service-Token"] == "svc-token"

    adjust_response = client.post(
        f"/items/{item['id']}/adjust",
        json={"delta": -6, "reason": "sale"},
        headers=auth_header(token),
    )
    assert adjust_response.status_code == 200, adjust_response.text
    body = adjust_response.json()
    assert body["new_quantity"] == 4
    assert len(requests) == 3  # log + notifier after adjustment crosses reorder point

    list_response = client.get("/items", headers=auth_header(token))
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1

    summary_response = client.get("/summary", headers=auth_header(token))
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_items"] == 1
    assert summary["low_stock"][0]["id"] == item["id"]


def test_prevent_negative_stock(inventory_client: Tuple[TestClient, object, List[Dict[str, Any]]]) -> None:
    client, module, requests = inventory_client
    token = build_token(module)

    create_payload = {
        "sku": "SKU-NEG",
        "name": "Negative Guard",
        "quantity": 1,
        "reorder_point": 0,
        "tenant_id": "test-tenant",
    }

    create_response = client.post("/items", json=create_payload, headers=auth_header(token))
    assert create_response.status_code == 201, create_response.text

    adjust_response = client.post(
        f"/items/{create_response.json()['id']}/adjust",
        json={"delta": -2},
        headers=auth_header(token),
    )
    assert adjust_response.status_code == 400
    assert "Quantity cannot be negative" in adjust_response.text
    assert len(requests) == 1  # only the create log call was issued
