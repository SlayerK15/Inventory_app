"""Audit log service with persistent storage and JWT-aware endpoints."""
from __future__ import annotations

from datetime import datetime
import os
from typing import Any, Dict, Generator, List, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field as SQLField, Session, SQLModel, create_engine, select

DEFAULT_DATABASE_URL = "sqlite:///./logs.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "service-token")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})


class AuditLog(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    actor_id: Optional[int] = SQLField(default=None, index=True)
    message: str
    metadata: Dict[str, Any] = SQLField(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class AuditLogWrite(BaseModel):
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditLogRead(BaseModel):
    id: int
    actor_id: Optional[int]
    message: str
    metadata: Dict[str, object]
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
    except ValueError as exc:  # pragma: no cover - invalid format
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


app = FastAPI(title="Log Service", version="1.0.0")
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


@app.post("/logs", response_model=AuditLogRead, tags=["logs"], status_code=status.HTTP_201_CREATED)
def create_log(
    payload: AuditLogWrite,
    token: str = Depends(extract_token),
    service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
    session: Session = Depends(get_session),
) -> AuditLogRead:
    if service_token != SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")
    actor_id = resolve_subject(token)
    log_entry = AuditLog(actor_id=actor_id, message=payload.message, metadata=payload.metadata)
    session.add(log_entry)
    session.commit()
    session.refresh(log_entry)
    return AuditLogRead.from_orm(log_entry)


@app.get("/logs", response_model=List[AuditLogRead], tags=["logs"])
def list_logs(token: str = Depends(extract_token), session: Session = Depends(get_session)) -> List[AuditLogRead]:
    resolve_subject(token)
    logs = session.exec(select(AuditLog).order_by(AuditLog.created_at.desc())).all()
    return [AuditLogRead.from_orm(log) for log in logs]
