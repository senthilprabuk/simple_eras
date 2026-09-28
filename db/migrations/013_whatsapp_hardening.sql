-- =====================================================================
-- Migration: 013_whatsapp_hardening.sql
-- Purpose:
--   Tighten the WhatsApp tables added in 011 and 012.
--
--   The Meta access token is a long-lived credential. eras_app, the role
--   every clinician request runs as, now reads every column of
--   meta.hospital_whatsapp but that one, as it cannot read password
--   hashes; the few paths that need the token use the connecting role.
--
--   Check-in links are credentials for a patient's day. They are minted
--   when a reminder is sent and no longer stored, and the ones stored so
--   far go with their columns.
--
--   attempts lets a send that failed for a passing reason (a timeout, a
--   Meta outage) be retried by the dispatcher; the queued index keeps its
--   scan for waiting messages cheap, like notification_queued.
--
--   hospital_whatsapp.updated_at gets the trigger every other table has;
--   01_meta.sql created it, 012 did not.
--
--   The seeded check-in confirmation stops telling every patient their
--   recovery is on track: it now also follows a check-in that the nurses
--   need to review. A hospital that already rewrote it keeps its wording.
-- =====================================================================

alter table txn.patient_message
    drop column if exists magic_token,
    drop column if exists magic_url,
    add column if not exists attempts integer not null default 0;

create index if not exists patient_message_queued
    on txn.patient_message (created_at)
    where status = 'queued';

drop trigger if exists hospital_whatsapp_touch on meta.hospital_whatsapp;
create trigger hospital_whatsapp_touch before update on meta.hospital_whatsapp
    for each row execute function meta.set_updated_at();

revoke select on meta.hospital_whatsapp from eras_app;
grant select (account_id, hospital_id, display_name, display_phone_number, phone_number_id,
              waba_id, verify_token, meta_app_id, health_status, is_default, is_active,
              created_at, updated_at)
    on meta.hospital_whatsapp to eras_app;

update meta.message_template
set body = 'Thank you {patient_first_name}. Your day {post_op_day} check-in has reached {hospital_name}.'
where template_key = 'checkin_confirmation'
  and language_code = 'en'
  and body = 'Thank you {patient_first_name}. Your Day {post_op_day} check-in has been received and your recovery is on track. Keep up with your exercises.';
