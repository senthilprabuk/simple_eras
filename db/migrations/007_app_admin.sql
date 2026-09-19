-- =====================================================================
-- Migration: 007_app_admin.sql
-- Purpose:
--   A platform administrator who manages hospitals and scoring rulesets
--   across every tenant, but never sees a patient.
--   1. meta.admin_user: role 'app_admin', held by accounts that belong to
--      no hospital. Their email is unique among app admins.
--   2. eras_platform: the database role app-admin requests switch to. It
--      reads and changes hospitals and rulesets, has no access to the txn
--      schema at all, and sees patients only as counts, through
--      meta.platform_usage().
--   3. Rulesets change only while they are drafts. Row-level security
--      stops eras_platform touching a published ruleset's parameters, and
--      a trigger stops anyone changing a published ruleset except to
--      retire it: enrolled patients stay scored by the rules they were
--      enrolled under.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

-- 1. App admin accounts --------------------------------------------------
alter table meta.admin_user alter column hospital_id drop not null;

alter table meta.admin_user drop constraint admin_user_role_known;
alter table meta.admin_user
    add constraint admin_user_role_known
        check (role in ('admin', 'superadmin', 'app_admin')),
    -- app admins work across hospitals; everyone else belongs to exactly one
    add constraint admin_user_app_admin_has_no_hospital
        check ((role = 'app_admin') = (hospital_id is null));

create unique index admin_user_app_admin_email
    on meta.admin_user (email)
    where hospital_id is null;


-- 2. The platform role ---------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'eras_platform') then
        create role eras_platform nologin nobypassrls;
    end if;
end $$;

grant eras_platform to current_user;
grant usage on schema meta to eras_platform;

grant select on meta.surgical_procedure, meta.parameter, meta.parameter_option to eras_platform;
grant select, insert, update on meta.hospital, meta.hospital_procedure to eras_platform;
grant select, insert, update, delete on meta.ruleset, meta.procedure_parameter to eras_platform;
-- hospital accounts: names and roles, never password hashes; new accounts may be created
grant select (admin_user_id, hospital_id, email, full_name, role, is_active, created_at)
    on meta.admin_user to eras_platform;
grant insert (hospital_id, email, hashed_password, full_name, role)
    on meta.admin_user to eras_platform;

create policy platform_all on meta.hospital to eras_platform using (true) with check (true);
create policy platform_all on meta.hospital_procedure to eras_platform using (true) with check (true);

-- Patient numbers without patient rows. Runs as its owner, so it can count
-- across tenants; it returns counts and nothing else.
create or replace function meta.platform_usage()
returns table (hospital_id integer, ruleset_id integer, active_episodes bigint, total_episodes bigint)
language sql stable security definer
set search_path = pg_catalog
as $$
    select e.hospital_id, e.ruleset_id,
           count(*) filter (where e.status = 'active'),
           count(*)
    from txn.patient_episode e
    group by e.hospital_id, e.ruleset_id
$$;

revoke all on function meta.platform_usage() from public;
grant execute on function meta.platform_usage() to eras_platform;


-- 3. Only drafts change --------------------------------------------------
alter table meta.ruleset             enable row level security;
alter table meta.procedure_parameter enable row level security;

-- clinicians read every ruleset and never change one
create policy readable on meta.ruleset             for select to eras_app, eras_platform using (true);
create policy readable on meta.procedure_parameter for select to eras_app, eras_platform using (true);

-- the platform starts drafts, edits and discards them, and publishes or retires versions
create policy platform_drafts  on meta.ruleset for insert to eras_platform with check (status = 'draft');
create policy platform_publish on meta.ruleset for update to eras_platform
    using (status in ('draft', 'approved')) with check (true);
create policy platform_discard on meta.ruleset for delete to eras_platform using (status = 'draft');

create policy platform_edit_drafts on meta.procedure_parameter for all to eras_platform
    using      (ruleset_id in (select ruleset_id from meta.ruleset where status = 'draft'))
    with check (ruleset_id in (select ruleset_id from meta.ruleset where status = 'draft'));

create or replace function meta.ruleset_guard() returns trigger
language plpgsql as $$
begin
    if old.status = 'draft' then
        return new;
    end if;
    -- a published version may be retired, and nothing else about it may change
    if old.status = 'approved' and new.status = 'retired'
       and (new.procedure_id, new.version, new.review_at, new.critical_at, new.max_points_per_parameter,
            new.approved_by, new.approved_at, new.notes)
           is not distinct from
           (old.procedure_id, old.version, old.review_at, old.critical_at, old.max_points_per_parameter,
            old.approved_by, old.approved_at, old.notes)
    then
        return new;
    end if;
    raise exception 'ruleset % is %; only a draft can be changed', old.version, old.status
        using errcode = 'check_violation';
end $$;

create trigger ruleset_guard before update on meta.ruleset
    for each row execute function meta.ruleset_guard();
