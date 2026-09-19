-- =====================================================================
-- Migration: 003_schema_hardening.sql
-- Purpose:
--   1. Store admin_user emails lowercase, making the (hospital_id, email)
--      unique constraint case-insensitive. Fails loudly if two accounts
--      at one hospital differ only by case; resolve those by hand first.
--   2. Require an episode's hospital to match its patient's hospital.
--   3. Index the notification dispatcher's queue.
--   4. Make v_alert_queue evaluate row-level security as the caller, and
--      expose each hospital's acknowledgement window.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

update meta.admin_user
   set email = lower(trim(email))
 where email <> lower(trim(email));

alter table meta.admin_user
    add constraint admin_user_email_lowercase check (email = lower(email));

alter table txn.patient
    add constraint patient_id_hospital_unique unique (patient_id, hospital_id);

alter table txn.patient_episode
    add constraint episode_patient_same_hospital
        foreign key (patient_id, hospital_id) references txn.patient (patient_id, hospital_id);

create index if not exists notification_queued
    on txn.alert_notification (created_at)
    where status = 'queued';

-- Columns may only be appended: CREATE OR REPLACE VIEW cannot reorder them.
create or replace view txn.v_alert_queue
with (security_invoker = true) as
select
    a.alert_id,
    a.tier,
    a.status,
    a.raised_at,
    (extract(epoch from (now() - a.raised_at)))::integer as age_secs,
    (a.acknowledged_at is not null)                      as acknowledged,
    a.acknowledged_at,
    a.acknowledged_by,
    au.full_name                                         as acknowledged_by_name,
    pt.patient_id,
    pt.patient_name,
    pt.mrn,
    e.episode_id,
    e.hospital_id,
    h.hospital_name,
    sp.procedure_code,
    ev.day_after_discharge,
    ev.reasons,
    h.ack_window_secs
from txn.alert a
join txn.check_in_evaluation ev  on ev.evaluation_id = a.evaluation_id
join txn.patient_episode e       on e.episode_id     = a.episode_id
join txn.patient pt              on pt.patient_id    = e.patient_id
join meta.hospital h             on h.hospital_id    = e.hospital_id
join meta.surgical_procedure sp  on sp.procedure_id  = e.procedure_id
left join meta.admin_user au     on au.admin_user_id = a.acknowledged_by
where a.status in ('open', 'acknowledged')
order by
    case a.tier
        when 'emergency' then 1
        when 'critical'  then 2
        when 'review'    then 3
        when 'missed'    then 4
        else 5
    end,
    a.raised_at asc;
