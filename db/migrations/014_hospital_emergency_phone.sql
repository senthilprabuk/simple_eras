-- =====================================================================
-- Migration: 014_hospital_emergency_phone.sql
-- Purpose:
--   The number a patient reporting an emergency symptom is told to call.
--
--   The check-in's "Call the ward" button dialled one hard-coded number
--   for every hospital. Each hospital now keeps its own, which a
--   superadmin sets in hospital settings and which message wording can
--   use as {hospital_phone}. Until it is set, the check-in points the
--   patient to emergency services instead of a number nobody answers.
-- =====================================================================

alter table meta.hospital add column if not exists emergency_phone_e164 text;

alter table meta.hospital drop constraint if exists hospital_emergency_phone_e164;
alter table meta.hospital add constraint hospital_emergency_phone_e164
    check (emergency_phone_e164 ~ '^\+[1-9][0-9]{7,14}$');

grant update (emergency_phone_e164) on meta.hospital to eras_app;
