-- =====================================================================
--  Views
--
--  Requires: 01_meta.sql, 02_txn.sql
--  Safe to re-run on its own after changing a view definition.
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- v_alert_queue   (the nurse triage queue)
--   hospital_id is selected so the API can scope every read to the
--   caller's tenant. Callers must still apply their own ORDER BY:
--   PostgreSQL does not guarantee that a view's ordering survives an
--   outer query that adds predicates.
-- ---------------------------------------------------------------------
create or replace view txn.v_alert_queue as
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
    ev.reasons
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

commit;
