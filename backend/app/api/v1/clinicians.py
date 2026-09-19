"""
Clinician accounts and the caller's own password.

These endpoints read and write password hashes, which the tenant-scoped role
cannot see, so they use get_system_db. Row-level security therefore does not
apply here: every query filters on the caller's hospital explicitly.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.login_throttle import login_throttle
from app.core.security import (
    AuthenticatedAdmin,
    get_current_admin,
    get_password_hash,
    require_superadmin,
    verify_password,
)
from app.db.session import get_system_db
from app.schemas.clinician import Clinician, ClinicianCreate, ClinicianUpdate, PasswordChange

router = APIRouter(tags=["Clinicians"])

CLINICIAN_COLUMNS = "admin_user_id, email, full_name, role, is_active, created_at"

@router.get("/clinicians", response_model=List[Clinician])
async def list_clinicians(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_system_db),
):
    rows = (await db.execute(text(f"""
        SELECT {CLINICIAN_COLUMNS} FROM meta.admin_user
        WHERE hospital_id = :h_id
        ORDER BY is_active DESC, full_name
    """), {"h_id": current_admin.hospital_id})).mappings().all()
    return [Clinician(**r) for r in rows]

@router.post("/clinicians", response_model=Clinician, status_code=status.HTTP_201_CREATED)
async def create_clinician(
    new: ClinicianCreate,
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_system_db),
):
    hashed = await run_in_threadpool(get_password_hash, new.password)
    try:
        row = (await db.execute(text(f"""
            INSERT INTO meta.admin_user (hospital_id, email, hashed_password, full_name, role)
            VALUES (:h_id, :email, :pwd, :name, :role)
            RETURNING {CLINICIAN_COLUMNS}
        """), {
            "h_id": current_admin.hospital_id, "email": new.email, "pwd": hashed,
            "name": new.full_name, "role": new.role,
        })).mappings().one()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A clinician with this email already exists here")
    return Clinician(**row)

@router.patch("/clinicians/{admin_user_id}", response_model=Clinician)
async def update_clinician(
    admin_user_id: UUID,
    changes: ClinicianUpdate,
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_system_db),
):
    """Change role or deactivate. Nobody can do either to themselves, so a hospital is never left without a superadmin by accident."""
    if admin_user_id == current_admin.admin_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role or deactivate yourself")

    row = (await db.execute(text(f"""
        UPDATE meta.admin_user
           SET role = coalesce(:role, role),
               is_active = coalesce(:active, is_active)
         WHERE admin_user_id = :id AND hospital_id = :h_id
        RETURNING {CLINICIAN_COLUMNS}
    """), {
        "id": admin_user_id, "h_id": current_admin.hospital_id,
        "role": changes.role, "active": changes.is_active,
    })).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Clinician not found")
    await db.commit()
    return Clinician(**row)

@router.post("/account/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    change: PasswordChange,
    request: Request,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_system_db),
):
    """Change your own password. Wrong current passwords count toward the sign-in throttle."""
    client = request.client.host if request.client else "unknown"
    if login_throttle.is_blocked(client, current_admin.email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts. Try again later.")

    stored = (await db.execute(
        text("SELECT hashed_password FROM meta.admin_user WHERE admin_user_id = :id AND hospital_id = :h_id"),
        {"id": current_admin.admin_user_id, "h_id": current_admin.hospital_id},
    )).scalar_one()

    if not await run_in_threadpool(verify_password, change.current_password, stored):
        login_throttle.record_failure(client, current_admin.email)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    hashed = await run_in_threadpool(get_password_hash, change.new_password)
    await db.execute(
        text("UPDATE meta.admin_user SET hashed_password = :pwd WHERE admin_user_id = :id AND hospital_id = :h_id"),
        {"pwd": hashed, "id": current_admin.admin_user_id, "h_id": current_admin.hospital_id},
    )
    await db.commit()
    login_throttle.record_success(client, current_admin.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
