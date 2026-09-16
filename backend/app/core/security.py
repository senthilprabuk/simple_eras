from datetime import datetime, timedelta, timezone
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
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

class AuthenticatedAdmin(BaseModel):
    admin_user_id: UUID
    hospital_id: int
    email: str
    full_name: str
    role: str

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

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
    FastAPI dependency: authenticates and verifies current admin from Bearer JWT.
    Enforces active status in meta.admin_user and scopes hospital_id.
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

    # Query meta.admin_user to verify identity and active status
    query = text("""
        SELECT admin_user_id, hospital_id, email, full_name, role, is_active
        FROM meta.admin_user
        WHERE admin_user_id = :admin_id AND hospital_id = :h_id;
    """)
    result = await db.execute(query, {"admin_id": admin_uuid, "h_id": hospital_id})
    row = result.fetchone()

    if not row or not row.is_active:
        raise credentials_exception

    return AuthenticatedAdmin(
        admin_user_id=row.admin_user_id,
        hospital_id=row.hospital_id,
        email=row.email,
        full_name=row.full_name,
        role=row.role
    )
