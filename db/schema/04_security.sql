-- =====================================================================
--  Tenant isolation — row-level security
--
--  Requires: 01_meta.sql, 02_txn.sql, 03_views.sql
--
--  The application connects as a role with BYPASSRLS (neondb_owner on
--  Neon), and table owners are exempt from their own policies anyway, so
--  policies alone would be silently ignored. Instead, each authenticated
--  clinician request switches role for the length of its transaction:
--
--      set local role eras_app;
--      select set_config('app.hospital_id', '<id>', true);
--
--  eras_app has no BYPASSRLS and only the privileges the dashboard needs.
--  A query that forgets its hospital filter still sees only that
--  hospital's rows, and with no hospital set it sees nothing at all.
--
--  System work — escalation sweep, notification dispatch, seeds and
--  migrations — keeps running as the connecting role, across tenants.
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- The tenant-scoped role
-- ---------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'eras_app') then
        create role eras_app nologin nobypassrls;
    end if;
end $$;

-- lets the connecting role SET ROLE into eras_app
grant eras_app to current_user;

-- App-admin requests switch to eras_platform instead: hospitals and rulesets
-- across every tenant, and no access to patient data (section at the end).
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'eras_platform') then
        create role eras_platform nologin nobypassrls;
    end if;
end $$;

grant eras_platform to current_user;

create or replace function meta.current_hospital_id() returns integer
language sql stable as $$
    select nullif(current_setting('app.hospital_id', true), '')::integer
$$;


-- ---------------------------------------------------------------------
-- Privileges — read the clinical record, change only the alert workflow
-- ---------------------------------------------------------------------
grant usage on schema meta, txn to eras_app;

grant select on
    meta.hospital, meta.surgical_procedure, meta.hospital_procedure,
    meta.parameter, meta.parameter_option, meta.ruleset, meta.procedure_parameter
to eras_app;

-- names for attribution only: no email, no password hash
grant select (admin_user_id, hospital_id, full_name, role, is_active)
    on meta.admin_user to eras_app;

grant select on
    txn.patient, txn.patient_contact, txn.patient_episode, txn.episode_baseline, txn.episode_consent,
    txn.patient_check_in, txn.patient_check_in_value,
    txn.check_in_evaluation, txn.alert, txn.alert_notification,
    txn.v_alert_queue
to eras_app;

grant update (status, acknowledged_at, acknowledged_by,
              resolved_at, resolved_by, outcome, outcome_note)
    on txn.alert to eras_app;

-- enrollment; a returning patient's details are refreshed when re-enrolled
grant insert on txn.patient, txn.patient_episode, txn.episode_baseline, txn.episode_consent to eras_app;
grant insert, delete on txn.patient_contact to eras_app;
grant update (phone_e164, language_code, date_of_birth, gender,
              address_line, address_city, address_district, address_state, address_postal_code,
              alt_phone_e164, email)
    on txn.patient to eras_app;

-- hospital settings and WhatsApp templates
grant update (hospital_name, city, timezone, ack_window_secs, emergency_phone_e164) on meta.hospital to eras_app;
grant select, insert, update on meta.message_template to eras_app;
grant select, insert, update on txn.patient_message to eras_app;
-- every column but the Meta access token, a long-lived credential
grant select (account_id, hospital_id, display_name, display_phone_number, phone_number_id,
              waba_id, verify_token, meta_app_id, health_status, is_default, is_active,
              created_at, updated_at)
    on meta.hospital_whatsapp to eras_app;
grant insert, update, delete on meta.hospital_whatsapp to eras_app;


-- ---------------------------------------------------------------------
-- Policies — every clinical row resolves to a hospital via its episode
-- ---------------------------------------------------------------------
alter table txn.patient                enable row level security;
alter table txn.patient_contact        enable row level security;
alter table txn.patient_episode        enable row level security;
alter table txn.episode_baseline       enable row level security;
alter table txn.episode_consent        enable row level security;
alter table txn.patient_check_in       enable row level security;
alter table txn.patient_check_in_value enable row level security;
alter table txn.check_in_evaluation    enable row level security;
alter table txn.alert                  enable row level security;
alter table txn.alert_notification     enable row level security;
alter table txn.patient_message        enable row level security;

create policy tenant_isolation on txn.patient to eras_app
    using (hospital_id = meta.current_hospital_id());

create policy tenant_isolation on txn.patient_episode to eras_app
    using (hospital_id = meta.current_hospital_id());

create policy tenant_isolation on txn.patient_message to eras_app
    using (hospital_id = meta.current_hospital_id());

create policy tenant_isolation on txn.patient_contact to eras_app
    using (patient_id in (select patient_id from txn.patient
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.episode_baseline to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.episode_consent to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.patient_check_in to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.check_in_evaluation to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.alert to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.patient_check_in_value to eras_app
    using (check_in_id in (select c.check_in_id
                           from txn.patient_check_in c
                           join txn.patient_episode e on e.episode_id = c.episode_id
                           where e.hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.alert_notification to eras_app
    using (alert_id in (select a.alert_id
                        from txn.alert a
                        join txn.patient_episode e on e.episode_id = a.episode_id
                        where e.hospital_id = meta.current_hospital_id()));

-- Hospital-owned reference rows: a tenant sees and edits only its own.
-- Shared reference data (parameters, procedures, rulesets) stays readable.
alter table meta.hospital           enable row level security;
alter table meta.hospital_procedure enable row level security;
alter table meta.message_template   enable row level security;
alter table meta.hospital_whatsapp  enable row level security;

create policy tenant_isolation on meta.hospital to eras_app
    using (hospital_id = meta.current_hospital_id());

create policy tenant_isolation on meta.hospital_procedure to eras_app
    using (hospital_id = meta.current_hospital_id());

create policy tenant_isolation on meta.message_template to eras_app
    using (hospital_id = meta.current_hospital_id());

create policy tenant_isolation on meta.hospital_whatsapp to eras_app
    using (hospital_id = meta.current_hospital_id());


-- ---------------------------------------------------------------------
-- The platform role — hospitals and rulesets, never a patient
-- ---------------------------------------------------------------------
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

-- Rulesets: everyone reads them; only drafts change (see meta.ruleset_guard).
alter table meta.ruleset             enable row level security;
alter table meta.procedure_parameter enable row level security;

create policy readable on meta.ruleset             for select to eras_app, eras_platform using (true);
create policy readable on meta.procedure_parameter for select to eras_app, eras_platform using (true);

create policy platform_drafts  on meta.ruleset for insert to eras_platform with check (status = 'draft');
create policy platform_publish on meta.ruleset for update to eras_platform
    using (status in ('draft', 'approved')) with check (true);
create policy platform_discard on meta.ruleset for delete to eras_platform using (status = 'draft');

create policy platform_edit_drafts on meta.procedure_parameter for all to eras_platform
    using      (ruleset_id in (select ruleset_id from meta.ruleset where status = 'draft'))
    with check (ruleset_id in (select ruleset_id from meta.ruleset where status = 'draft'));


-- ---------------------------------------------------------------------
-- Migrations whose effect this baseline already contains
--   Add a row here whenever a new migration is folded into db/schema/.
-- ---------------------------------------------------------------------
insert into meta.schema_migration (version, name) values
    ('001', '001_admin_user_and_fk_cleanup'),
    ('002', '002_remove_redness_parameter'),
    ('003', '003_schema_hardening'),
    ('004', '004_row_level_security'),
    ('005', '005_admin_screens'),
    ('006', '006_enrollment_safety_data'),
    ('007', '007_app_admin'),
    ('008', '008_rule_direction'),
    ('009', '009_composite_signals'),
    ('010', '010_operative_side'),
    ('011', '011_patient_messages'),
    ('012', '012_hospital_whatsapp'),
    ('013', '013_whatsapp_hardening'),
    ('014', '014_hospital_emergency_phone')
on conflict (version) do nothing;

commit;
