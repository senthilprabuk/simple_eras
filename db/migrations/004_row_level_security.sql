-- =====================================================================
-- Migration: 004_row_level_security.sql
-- Purpose:
--   Enforce tenant isolation in the database, not only in application
--   queries. See db/schema/04_security.sql for the design: authenticated
--   clinician requests SET LOCAL ROLE eras_app and set app.hospital_id,
--   and eras_app can only see rows belonging to that hospital.
--
--   Creates the cluster-wide role eras_app if it does not exist yet.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'eras_app') then
        create role eras_app nologin nobypassrls;
    end if;
end $$;

grant eras_app to current_user;

create or replace function meta.current_hospital_id() returns integer
language sql stable as $$
    select nullif(current_setting('app.hospital_id', true), '')::integer
$$;

grant usage on schema meta, txn to eras_app;

grant select on
    meta.hospital, meta.surgical_procedure, meta.hospital_procedure,
    meta.parameter, meta.parameter_option, meta.ruleset, meta.procedure_parameter
to eras_app;

grant select (admin_user_id, hospital_id, full_name, role, is_active)
    on meta.admin_user to eras_app;

grant select on
    txn.patient, txn.patient_episode, txn.episode_baseline,
    txn.patient_check_in, txn.patient_check_in_value,
    txn.check_in_evaluation, txn.alert, txn.alert_notification,
    txn.v_alert_queue
to eras_app;

grant update (status, acknowledged_at, acknowledged_by,
              resolved_at, resolved_by, outcome, outcome_note)
    on txn.alert to eras_app;

alter table txn.patient                enable row level security;
alter table txn.patient_episode        enable row level security;
alter table txn.episode_baseline       enable row level security;
alter table txn.patient_check_in       enable row level security;
alter table txn.patient_check_in_value enable row level security;
alter table txn.check_in_evaluation    enable row level security;
alter table txn.alert                  enable row level security;
alter table txn.alert_notification     enable row level security;

drop policy if exists tenant_isolation on txn.patient;
create policy tenant_isolation on txn.patient to eras_app
    using (hospital_id = meta.current_hospital_id());

drop policy if exists tenant_isolation on txn.patient_episode;
create policy tenant_isolation on txn.patient_episode to eras_app
    using (hospital_id = meta.current_hospital_id());

drop policy if exists tenant_isolation on txn.episode_baseline;
create policy tenant_isolation on txn.episode_baseline to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

drop policy if exists tenant_isolation on txn.patient_check_in;
create policy tenant_isolation on txn.patient_check_in to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

drop policy if exists tenant_isolation on txn.check_in_evaluation;
create policy tenant_isolation on txn.check_in_evaluation to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

drop policy if exists tenant_isolation on txn.alert;
create policy tenant_isolation on txn.alert to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));

drop policy if exists tenant_isolation on txn.patient_check_in_value;
create policy tenant_isolation on txn.patient_check_in_value to eras_app
    using (check_in_id in (select c.check_in_id
                           from txn.patient_check_in c
                           join txn.patient_episode e on e.episode_id = c.episode_id
                           where e.hospital_id = meta.current_hospital_id()));

drop policy if exists tenant_isolation on txn.alert_notification;
create policy tenant_isolation on txn.alert_notification to eras_app
    using (alert_id in (select a.alert_id
                        from txn.alert a
                        join txn.patient_episode e on e.episode_id = a.episode_id
                        where e.hospital_id = meta.current_hospital_id()));
