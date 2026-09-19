from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from uuid import UUID
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db, scope_to_hospital

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

class AuthenticatedAdmin(BaseModel):
    admin_user_id: UUID
    hospital_id: int
    email: str
    full_name: str
    role: str

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash. Blocking: call off the event loop."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except ValueError:
        return False

@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return get_password_hash("timing-equaliser-not-a-real-password")

def burn_password_check(plain_password: str) -> None:
    """Spend the same bcrypt time as a real check, so timing never reveals that an account is missing."""
    verify_password(plain_password, _dummy_hash())

def get_password_hash(password: str) -> str:
    """Generate a bcrypt password hash."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encode a signed JWT access token with expiration and admin claims."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> AuthenticatedAdmin:
    """
    Authenticate the Bearer JWT against an active meta.admin_user row, then scope
    the request's database session to that admin's hospital. FastAPI shares the
    get_db session with the endpoint, so every query the endpoint runs is scoped.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or inactive account",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    admin_user_id_str: Optional[str] = payload.get("sub")
    hospital_id: Optional[int] = payload.get("hospital_id")

    if not admin_user_id_str or hospital_id is None:
        raise credentials_exception

    try:
        admin_uuid = UUID(admin_user_id_str)
    except ValueError:
        raise credentials_exception

    query = text("""
        SELECT admin_user_id, hospital_id, email, full_name, role, is_active
        FROM meta.admin_user
        WHERE admin_user_id = :admin_id AND hospital_id = :h_id;
    """)
    result = await db.execute(query, {"admin_id": admin_uuid, "h_id": hospital_id})
    row = result.fetchone()

    if not row or not row.is_active:
        raise credentials_exception

    await scope_to_hospital(db, row.hospital_id)

    return AuthenticatedAdmin(
        admin_user_id=row.admin_user_id,
        hospital_id=row.hospital_id,
        email=row.email,
        full_name=row.full_name,
        role=row.role
    )

async def require_superadmin(admin: AuthenticatedAdmin = Depends(get_current_admin)) -> AuthenticatedAdmin:
    if admin.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a superadmin can make this change")
    return admin
