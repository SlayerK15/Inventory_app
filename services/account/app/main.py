"""Account service with persistent storage and JWT authentication."""
from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Generator, List, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Field as SQLField, Session, SQLModel, create_engine, select

DEFAULT_DATABASE_URL = "sqlite:///./account.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ALGORITHM = "HS256"
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "password123")
DEFAULT_ADMIN_NAME = os.getenv("DEFAULT_ADMIN_NAME", "Inventory Manager")
DEFAULT_ADMIN_TENANT = os.getenv("DEFAULT_ADMIN_TENANT", "default-tenant")
DEFAULT_ADMIN_ROLE = os.getenv("DEFAULT_ADMIN_ROLE", "manager")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})


class User(SQLModel, table=True):
    """Database model representing an authenticated platform user."""

    id: Optional[int] = SQLField(default=None, primary_key=True)
    email: EmailStr = SQLField(index=True, unique=True)
    full_name: str = SQLField(index=True)
    role: str = SQLField(default="viewer")
    tenant_id: str = SQLField(index=True)
    hashed_password: str
    created_at: datetime = SQLField(default_factory=datetime.utcnow, nullable=False)


class UserCreate(BaseModel):
    """Payload used to register a new user."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str = Field(default="viewer")
    tenant_id: str


class UserLogin(BaseModel):
    """Credentials used when requesting an access token."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Standard access token wrapper."""

    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    """Response model without the password column."""

    id: int
    email: EmailStr
    full_name: str
    role: str
    tenant_id: str
    created_at: datetime

    class Config:
        orm_mode = True


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def extract_token(authorization: Optional[str] = Header(default=None)) -> str:
    return _extract_token(authorization)


def get_current_user(
    token: str = Depends(extract_token),
    session: Session = Depends(get_session),
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = session.exec(select(User).where(User.id == int(user_id))).one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _extract_token(authorization: Optional[str] = None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    try:
        scheme, token = authorization.split()
    except ValueError as exc:  # pragma: no cover - invalid format
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header") from exc
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported authorization scheme")
    return token


app = FastAPI(title="Account Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    ,
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_default_user()


@app.get("/healthz", tags=["ops"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/register", response_model=UserRead, tags=["auth"], status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, session: Session = Depends(get_session)) -> UserRead:
    existing = session.exec(select(User).where(User.email == payload.email)).one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        tenant_id=payload.tenant_id,
        hashed_password=get_password_hash(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserRead.from_orm(user)


@app.post("/login", response_model=TokenResponse, tags=["auth"])
def login(payload: UserLogin, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.exec(select(User).where(User.email == payload.email)).one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@app.get("/users/me", response_model=UserRead, tags=["users"])
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.from_orm(current_user)


@app.get("/users", response_model=List[UserRead], tags=["users"])
def list_users(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> List[UserRead]:
    if current_user.role != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    users = session.exec(select(User)).all()
    return [UserRead.from_orm(user) for user in users]


@app.get("/verify", response_model=UserRead, tags=["auth"], include_in_schema=False)
def verify_token(current_user: User = Depends(get_current_user)) -> UserRead:
    """Endpoint used by other services to resolve tokens into user records."""

    return UserRead.from_orm(current_user)


def seed_default_user() -> None:
    if not DEFAULT_ADMIN_EMAIL:
        return
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == DEFAULT_ADMIN_EMAIL)).one_or_none()
        if existing:
            return
        user = User(
            email=DEFAULT_ADMIN_EMAIL,
            full_name=DEFAULT_ADMIN_NAME,
            role=DEFAULT_ADMIN_ROLE,
            tenant_id=DEFAULT_ADMIN_TENANT,
            hashed_password=get_password_hash(DEFAULT_ADMIN_PASSWORD),
        )
        session.add(user)
        session.commit()
