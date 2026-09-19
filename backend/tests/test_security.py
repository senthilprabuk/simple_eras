"""Row-level security: the database itself keeps each hospital's clinical rows apart."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import scope_to_hospital
from tests.conftest import isolated_session_factory
from tests.support import create_alert


async def _scalar_as(hospital_id, sql, **params):
    async with isolated_session_factory() as session:
        await scope_to_hospital(session, hospital_id)
        return (await session.execute(text(sql), params)).scalar_one()


async def test_queries_without_a_hospital_filter_still_see_one_hospital(db, second_hospital):
    h2_alert = await create_alert(db, second_hospital.episode_id, tier="review")

    # Deliberately no WHERE clause: the policies alone must keep tenants apart.
    assert await _scalar_as(second_hospital.hospital_id, "SELECT count(*) FROM txn.patient") == 1
    assert await _scalar_as(second_hospital.hospital_id, "SELECT count(*) FROM txn.alert") >= 1
    assert await _scalar_as(
        second_hospital.hospital_id,
        "SELECT count(*) FROM txn.alert a JOIN txn.patient_episode e USING (episode_id) WHERE e.hospital_id = 1",
    ) == 0
    assert await _scalar_as(1, "SELECT count(*) FROM txn.alert WHERE alert_id = :a", a=h2_alert) == 0
    assert await _scalar_as(1, "SELECT count(*) FROM txn.patient") == 12


async def test_tenant_role_without_a_hospital_sees_nothing():
    async with isolated_session_factory() as session:
        await session.execute(text("SET LOCAL ROLE eras_app"))
        assert (await session.execute(text("SELECT count(*) FROM txn.alert"))).scalar_one() == 0
        assert (await session.execute(text("SELECT count(*) FROM txn.v_alert_queue"))).scalar_one() == 0


async def test_tenant_role_cannot_read_password_hashes():
    async with isolated_session_factory() as session:
        await scope_to_hospital(session, 1)
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(text("SELECT hashed_password FROM meta.admin_user"))


async def test_tenant_role_cannot_rewrite_the_clinical_record():
    async with isolated_session_factory() as session:
        await scope_to_hospital(session, 1)
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(text("UPDATE txn.patient SET patient_name = 'changed'"))


async def test_tenant_scope_ends_at_commit():
    async with isolated_session_factory() as session:
        await scope_to_hospital(session, 999)
        assert (await session.execute(text("SELECT count(*) FROM txn.patient"))).scalar_one() == 0
        await session.commit()
        assert (await session.execute(text("SELECT current_user"))).scalar_one() != "eras_app"


async def test_hospital_settings_and_templates_are_tenant_scoped(second_hospital):
    # The fixture hospital has seeded templates; another tenant must not see them.
    assert await _scalar_as(second_hospital.hospital_id, "SELECT count(*) FROM meta.hospital") == 1
    assert await _scalar_as(second_hospital.hospital_id, "SELECT count(*) FROM meta.message_template") == 0
    assert await _scalar_as(1, "SELECT count(*) FROM meta.message_template") == 4


async def test_an_unfiltered_settings_update_changes_only_the_callers_hospital(db, second_hospital):
    async with isolated_session_factory() as session:
        await scope_to_hospital(session, second_hospital.hospital_id)
        changed = (await session.execute(text("UPDATE meta.hospital SET city = 'Scoped'"))).rowcount
        await session.rollback()
    assert changed == 1
