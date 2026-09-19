"""
WhatsApp message wording, per hospital, template and language. Stored for the
WhatsApp integration; nothing in this service sends messages yet.
"""

from typing import get_args

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedAdmin, get_current_admin, require_superadmin
from app.db.session import get_db
from app.schemas.template import (
    PLACEHOLDERS,
    TEMPLATE_PURPOSES,
    TemplateCatalogue,
    TemplateEntry,
    TemplateKey,
    TemplateLanguage,
    TemplateUpdate,
)

router = APIRouter(prefix="/templates", tags=["WhatsApp templates"])

async def _catalogue(db: AsyncSession, hospital_id: int) -> TemplateCatalogue:
    stored = {
        (r["template_key"], r["language_code"]): r
        for r in (await db.execute(text("""
            SELECT t.template_key, t.language_code, t.body, t.is_active, t.updated_at,
                   u.full_name AS updated_by_name
            FROM meta.message_template t
            LEFT JOIN meta.admin_user u ON u.admin_user_id = t.updated_by
            WHERE t.hospital_id = :h_id
        """), {"h_id": hospital_id})).mappings().all()
    }
    # Every key in every language, so a missing translation shows as a gap to fill.
    entries = [
        TemplateEntry(**stored[(key, lang)]) if (key, lang) in stored
        else TemplateEntry(template_key=key, language_code=lang)
        for key in get_args(TemplateKey)
        for lang in get_args(TemplateLanguage)
    ]
    return TemplateCatalogue(templates=entries, purposes=TEMPLATE_PURPOSES, placeholders=PLACEHOLDERS)

@router.get("", response_model=TemplateCatalogue)
async def list_templates(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _catalogue(db, current_admin.hospital_id)

@router.put("/{template_key}/{language_code}", response_model=TemplateEntry)
async def save_template(
    template_key: TemplateKey,
    language_code: TemplateLanguage,
    update: TemplateUpdate,
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Create or replace one template. Patient-facing wording, so superadmins only."""
    row = (await db.execute(text("""
        INSERT INTO meta.message_template (hospital_id, template_key, language_code, body, is_active, updated_by)
        VALUES (:h_id, :key, :lang, :body, :active, :admin_id)
        ON CONFLICT (hospital_id, template_key, language_code) DO UPDATE
            SET body = excluded.body, is_active = excluded.is_active, updated_by = excluded.updated_by
        RETURNING template_key, language_code, body, is_active, updated_at
    """), {
        "h_id": current_admin.hospital_id, "key": template_key, "lang": language_code,
        "body": update.body, "active": update.is_active, "admin_id": current_admin.admin_user_id,
    })).mappings().one()
    await db.commit()
    return TemplateEntry(**row, updated_by_name=current_admin.full_name)
