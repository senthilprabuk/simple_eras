from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models.meta import AdminUser
from app.schemas.auth import LoginRequest, TokenResponse
from app.core.security import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate hospital admin and return signed JWT access token.
    Supports optional hospital_id disambiguation when the same email
    exists across multiple hospital tenants.
    """
    # Build query
    query = select(AdminUser).where(AdminUser.email == req.email)
    if req.hospital_id is not None:
        query = query.where(AdminUser.hospital_id == req.hospital_id)

    result = await db.execute(query)
    admins: List[AdminUser] = list(result.scalars().all())

    # Handle multi-hospital email disambiguation
    if len(admins) > 1 and req.hospital_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple hospital accounts found for this email. Please provide hospital_id."
        )

    if not admins:
        # Generic message to avoid email enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    admin = admins[0]

    # Verify active status
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive. Please contact administrator.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Verify password
    if not verify_password(req.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Issue token with tenant claims
    token_data = {
        "sub": str(admin.admin_user_id),
        "hospital_id": admin.hospital_id,
        "role": admin.role
    }
    access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        admin_user_id=admin.admin_user_id,
        hospital_id=admin.hospital_id,
        full_name=admin.full_name,
        role=admin.role
    )
