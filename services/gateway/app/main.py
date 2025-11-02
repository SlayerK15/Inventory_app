"""Gateway service orchestrating authenticated access to microservices."""
from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class Settings(BaseModel):
    account_service_url: str = Field(default="http://account:8000")
    inventory_service_url: str = Field(default="http://inventory:8000")
    log_service_url: str = Field(default="http://log:8000")
    notifier_service_url: str = Field(default="http://notifier:8000")
    service_token: str = Field(default="service-token")

    class Config:
        env_prefix = "GATEWAY_"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings(
        account_service_url=os.getenv("GATEWAY_ACCOUNT_SERVICE_URL", "http://account:8000"),
        inventory_service_url=os.getenv("GATEWAY_INVENTORY_SERVICE_URL", "http://inventory:8000"),
        log_service_url=os.getenv("GATEWAY_LOG_SERVICE_URL", "http://log:8000"),
        notifier_service_url=os.getenv("GATEWAY_NOTIFIER_SERVICE_URL", "http://notifier:8000"),
        service_token=os.getenv("SERVICE_TOKEN", "service-token"),
    )


app = FastAPI(title="Inventory Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InventoryItem(BaseModel):
    id: int
    sku: str
    name: str
    description: str | None = None
    quantity: int
    location: str | None = None
    reorder_point: int
    tenant_id: str
    created_at: str
    updated_at: str


class UserProfile(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: str
    created_at: str


class DashboardSummary(BaseModel):
    user: UserProfile
    inventory: List[InventoryItem] = Field(default_factory=list)
    low_stock: List[InventoryItem] = Field(default_factory=list)


class InventoryCreate(BaseModel):
    sku: str
    name: str
    description: str | None = None
    quantity: int = Field(default=0, ge=0)
    location: str | None = None
    reorder_point: int = Field(default=0, ge=0)
    tenant_id: str = Field(default="default-tenant")


class StockAdjustment(BaseModel):
    delta: int
    reason: str | None = None


async def forward_request(
    method: str,
    url: str,
    token: Optional[str] = None,
    json: Optional[Dict[str, Any]] = None,
    service_token: Optional[str] = None,
) -> httpx.Response:
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if service_token:
        headers["X-Service-Token"] = service_token
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(method, url, json=json, headers=headers)
    except httpx.RequestError as exc:  # pragma: no cover - network failure
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return response


def extract_token(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    try:
        scheme, token = authorization.split()
    except ValueError as exc:  # pragma: no cover - invalid header
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header") from exc
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported authorization scheme")
    return token


async def fetch_json(url: str, token: Optional[str]) -> Any:
    response = await forward_request("GET", url, token=token)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/healthz", tags=["ops"])
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", tags=["auth"], status_code=status.HTTP_201_CREATED)
async def register_user(payload: Dict[str, Any], settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    response = await forward_request("POST", f"{settings.account_service_url}/register", json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.post("/auth/login", tags=["auth"])
async def login(payload: Dict[str, Any], settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    response = await forward_request("POST", f"{settings.account_service_url}/login", json=payload)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/me", response_model=UserProfile, tags=["account"])
async def get_profile(
    token: str = Depends(extract_token),
    settings: Settings = Depends(get_settings),
) -> UserProfile:
    payload = await fetch_json(f"{settings.account_service_url}/users/me", token)
    return UserProfile(**payload)


@app.get("/dashboard", response_model=DashboardSummary, tags=["dashboard"])
async def dashboard(
    token: str = Depends(extract_token),
    settings: Settings = Depends(get_settings),
) -> DashboardSummary:
    user_payload, items_payload, summary_payload = await asyncio.gather(
        fetch_json(f"{settings.account_service_url}/users/me", token),
        fetch_json(f"{settings.inventory_service_url}/items", token),
        fetch_json(f"{settings.inventory_service_url}/summary", token),
    )
    return DashboardSummary(
        user=UserProfile(**user_payload),
        inventory=[InventoryItem(**item) for item in items_payload],
        low_stock=[InventoryItem(**item) for item in summary_payload.get("low_stock", [])],
    )


@app.post("/inventory", response_model=InventoryItem, tags=["inventory"], status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    payload: InventoryCreate,
    token: str = Depends(extract_token),
    settings: Settings = Depends(get_settings),
) -> InventoryItem:
    response = await forward_request(
        "POST",
        f"{settings.inventory_service_url}/items",
        token=token,
        json=payload.dict(),
        service_token=settings.service_token,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return InventoryItem(**response.json())


@app.post("/inventory/{item_id}/adjust", tags=["inventory"], response_model=Dict[str, Any])
async def adjust_inventory(
    item_id: int,
    payload: StockAdjustment,
    token: str = Depends(extract_token),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    response = await forward_request(
        "POST",
        f"{settings.inventory_service_url}/items/{item_id}/adjust",
        token=token,
        json=payload.dict(),
        service_token=settings.service_token,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/logs", tags=["logs"], response_model=List[Dict[str, Any]])
async def list_logs(
    token: str = Depends(extract_token),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    response = await forward_request("GET", f"{settings.log_service_url}/logs", token=token)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/notifications", tags=["notifications"], response_model=List[Dict[str, Any]])
async def list_notifications(
    token: str = Depends(extract_token),
    settings: Settings = Depends(get_settings),
) -> List[Dict[str, Any]]:
    response = await forward_request("GET", f"{settings.notifier_service_url}/notify", token=token)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()
