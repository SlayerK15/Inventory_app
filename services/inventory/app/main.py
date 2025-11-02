"""Inventory service backed by SQL persistence and notification hooks."""
from __future__ import annotations

from datetime import datetime
import os
import time
from typing import Generator, List, Optional

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlmodel import Field as SQLField, Session, SQLModel, create_engine, select

DEFAULT_DATABASE_URL = "sqlite:///./inventory.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"
LOG_SERVICE_URL = os.getenv("LOG_SERVICE_URL", "http://log:8000")
NOTIFIER_SERVICE_URL = os.getenv("NOTIFIER_SERVICE_URL", "http://notifier:8000")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "service-token")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})


def wait_for_db(max_attempts: int = 10, delay_seconds: float = 1.0) -> None:
    """Block until the backing database is ready to accept connections."""

    last_exc: Optional[OperationalError] = None
    for _attempt in range(1, max_attempts + 1):
        try:
            with engine.connect():
                return
        except OperationalError as exc:  # pragma: no cover - depends on external DB readiness
            last_exc = exc
            time.sleep(delay_seconds)
    if last_exc is not None:
        raise last_exc


class InventoryItem(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    sku: str = SQLField(index=True, unique=True)
    name: str
    description: Optional[str] = None
    quantity: int = SQLField(default=0)
    location: Optional[str] = None
    reorder_point: int = SQLField(default=0)
    tenant_id: str = SQLField(default="default-tenant", index=True)
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class ItemCreate(BaseModel):
    sku: str
    name: str
    description: str | None = None
    quantity: int = Field(default=0, ge=0)
    location: str | None = None
    reorder_point: int = Field(default=0, ge=0)
    tenant_id: str = Field(default="default-tenant")


class ItemRead(BaseModel):
    id: int
    sku: str
    name: str
    description: str | None
    quantity: int
    location: str | None
    reorder_point: int
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class StockAdjustment(BaseModel):
    delta: int
    reason: str | None = None


class AdjustmentResponse(BaseModel):
    item: ItemRead
    new_quantity: int


class DashboardSummary(BaseModel):
    total_items: int
    low_stock: List[ItemRead]


def init_db() -> None:
    wait_for_db()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def extract_token(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    try:
        scheme, token = authorization.split()
    except ValueError as exc:  # pragma: no cover - invalid format
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header") from exc
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported authorization scheme")
    return token


def resolve_user(token: str) -> dict[str, str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:  # pragma: no cover - invalid token
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    return {"user_id": payload.get("sub")}


async def write_log(message: str, token: str, metadata: Optional[dict[str, str]] = None) -> None:
    payload = {"message": message, "metadata": metadata or {}}
    headers = {"Authorization": f"Bearer {token}", "X-Service-Token": SERVICE_TOKEN}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{LOG_SERVICE_URL}/logs", json=payload, headers=headers)
        response.raise_for_status()


async def send_notification(item: InventoryItem) -> None:
    payload = {
        "channel": "email",
        "recipient": "ops@example.com",
        "subject": f"Low stock alert: {item.name}",
        "message": f"Item {item.sku} has fallen to {item.quantity} units.",
    }
    headers = {"X-Service-Token": SERVICE_TOKEN}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{NOTIFIER_SERVICE_URL}/notify", json=payload, headers=headers)
        response.raise_for_status()


app = FastAPI(title="Inventory Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/healthz", tags=["ops"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED, tags=["items"])
async def create_item(
    payload: ItemCreate,
    token: str = Depends(extract_token),
    session: Session = Depends(get_session),
) -> ItemRead:
    resolve_user(token)
    session_item = session.exec(select(InventoryItem).where(InventoryItem.sku == payload.sku)).one_or_none()
    if session_item:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SKU already exists")
    item = InventoryItem(**payload.dict())
    session.add(item)
    session.commit()
    session.refresh(item)
    await write_log(f"Created item {item.sku}", token, {"item_id": str(item.id)})
    if item.quantity <= item.reorder_point and item.reorder_point > 0:
        await send_notification(item)
    return ItemRead.from_orm(item)


@app.get("/items", response_model=List[ItemRead], tags=["items"])
def list_items(token: str = Depends(extract_token), session: Session = Depends(get_session)) -> List[ItemRead]:
    resolve_user(token)
    items = session.exec(select(InventoryItem)).all()
    return [ItemRead.from_orm(item) for item in items]


@app.post("/items/{item_id}/adjust", response_model=AdjustmentResponse, tags=["items"])
async def adjust_item(
    item_id: int,
    payload: StockAdjustment,
    token: str = Depends(extract_token),
    session: Session = Depends(get_session),
) -> AdjustmentResponse:
    resolve_user(token)
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    new_quantity = item.quantity + payload.delta
    if new_quantity < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity cannot be negative")
    item.quantity = new_quantity
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    await write_log(
        f"Adjusted item {item.sku} by {payload.delta}",
        token,
        {"item_id": str(item.id), "reason": payload.reason or "adjustment"},
    )
    if item.quantity <= item.reorder_point and item.reorder_point > 0:
        await send_notification(item)
    return AdjustmentResponse(item=ItemRead.from_orm(item), new_quantity=item.quantity)


@app.get("/summary", response_model=DashboardSummary, tags=["items"])
def summary(token: str = Depends(extract_token), session: Session = Depends(get_session)) -> DashboardSummary:
    resolve_user(token)
    items = session.exec(select(InventoryItem)).all()
    low_stock = [item for item in items if item.reorder_point > 0 and item.quantity <= item.reorder_point]
    return DashboardSummary(
        total_items=len(items),
        low_stock=[ItemRead.from_orm(item) for item in low_stock],
    )
