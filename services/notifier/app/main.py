"""Notification service persisting delivery requests."""
from __future__ import annotations

from datetime import datetime
import os
from typing import Generator, List, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Session, SQLModel, create_engine, select

DEFAULT_DATABASE_URL = "sqlite:///./notifications.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "service-token")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})


class NotificationRequest(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    channel: str
    recipient: str
    subject: str
    message: str
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    status: str = SQLField(default="queued")


class NotificationCreate(BaseModel):
    channel: str = Field(description="email | sms | push")
    recipient: str
    subject: str
    message: str


class NotificationRead(BaseModel):
    id: int
    channel: str
    recipient: str
    subject: str
    message: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


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


def resolve_subject(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:  # pragma: no cover - invalid token
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return int(subject)


app = FastAPI(title="Notifier Service", version="1.0.0")
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


@app.post("/notify", response_model=NotificationRead, status_code=status.HTTP_201_CREATED, tags=["notifications"])
def send(
    payload: NotificationCreate,
    service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
    session: Session = Depends(get_session),
) -> NotificationRead:
    if service_token != SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")
    record = NotificationRequest(**payload.dict(), status="sent")
    session.add(record)
    session.commit()
    session.refresh(record)
    return NotificationRead.from_orm(record)


@app.get("/notify", response_model=List[NotificationRead], tags=["notifications"])
def history(token: str = Depends(extract_token), session: Session = Depends(get_session)) -> List[NotificationRead]:
    resolve_subject(token)
    notifications = session.exec(select(NotificationRequest).order_by(NotificationRequest.created_at.desc())).all()
    return [NotificationRead.from_orm(notification) for notification in notifications]
