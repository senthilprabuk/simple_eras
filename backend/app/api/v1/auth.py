from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.login_throttle import login_throttle
from app.core.security import burn_password_check, create_access_token, verify_password
from app.db.models.meta import AdminUser, Hospital
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate a hospital admin and return a signed JWT.

    Unknown, inactive and wrong-password sign-ins get the same 401, and every
    attempt performs at least one bcrypt check, so neither the message nor the
    timing reveals whether an account exists.
    """
    client = request.client.host if request.client else "unknown"
    if login_throttle.is_blocked(client, req.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
        )

    # App admins belong to no hospital; everyone else only while their hospital is active.
    query = select(AdminUser).where(
        AdminUser.email == req.email,
        AdminUser.is_active.is_(True),
        or_(AdminUser.hospital_id.is_(None),
            AdminUser.hospital_id.in_(select(Hospital.hospital_id).where(Hospital.is_active.is_(True)))),
    )
    if req.hospital_id is not None:
        query = query.where(AdminUser.hospital_id == req.hospital_id)
    candidates = list((await db.execute(query)).scalars().all())

    if candidates:
        matched = [
            admin for admin in candidates
            if await run_in_threadpool(verify_password, req.password, admin.hashed_password)
        ]
    else:
        await run_in_threadpool(burn_password_check, req.password)
        matched = []

    if not matched:
        login_throttle.record_failure(client, req.email)
        raise _invalid_credentials()

    hospitals = (await db.execute(
        text("""
            SELECT hospital_id, hospital_name FROM meta.hospital
            WHERE hospital_id = ANY(:ids) ORDER BY hospital_name
        """),
        {"ids": [admin.hospital_id for admin in matched]},
    )).mappings().all()

    if len(matched) > 1:
        # Only reachable with a correct password, so it tells a guesser nothing.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "This account exists at more than one hospital. Choose one to sign in.",
                "hospitals": [dict(h) for h in hospitals],
            },
        )

    login_throttle.record_success(client, req.email)
    admin = matched[0]
    access_token = create_access_token(data={
        "sub": str(admin.admin_user_id),
        "hospital_id": admin.hospital_id,
        "role": admin.role,
    })

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin_user_id=admin.admin_user_id,
        hospital_id=admin.hospital_id,
        hospital_name=hospitals[0]["hospital_name"] if admin.hospital_id is not None else None,
        full_name=admin.full_name,
        role=admin.role,
    )
