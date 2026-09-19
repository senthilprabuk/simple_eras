-- =====================================================================
-- Migration: 006_enrollment_safety_data.sql
-- Purpose:
--   Record what the care team needs when something goes wrong at home,
--   shaped so it maps onto FHIR when the record is exchanged.
--   1. txn.patient: administrative sex (Patient.gender), home address
--      for an ambulance or home visit (Patient.address), and a second
--      channel if WhatsApp fails: an SMS number and an email address
--      (Patient.telecom, rank 2).
--   2. txn.patient_contact: emergency contacts and caregivers, in the
--      order to call them (Patient.contact).
--   3. txn.patient_episode: the window the patient prefers for the daily
--      check-in, in the hospital's local time.
--   4. txn.episode_consent: one row per consent decision (Consent), under
--      the privacy law the hospital operates under (meta.hospital).
--   5. meta.parameter: height, weight and blood pressure as baseline-only
--      measures, and a LOINC code on each measure (Observation.code).
--   6. Grants and row-level security for the new tables.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

-- 1. Patient demographics ------------------------------------------------
alter table txn.patient
    add column gender              text not null default 'unknown',
    add column address_line        text,
    add column address_city        text,
    add column address_district    text,
    add column address_state       text,
    add column address_postal_code text,
    add column alt_phone_e164      text,
    add column email               text;

alter table txn.patient
    add constraint patient_gender_known   check (gender in ('male','female','other','unknown')),
    add constraint patient_postal_code    check (address_postal_code ~ '^[A-Za-z0-9 -]{3,10}$'),
    add constraint patient_alt_phone_e164 check (alt_phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
    add constraint patient_email_shape    check (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$');


-- 2. Emergency contacts ------------------------------------------------
create table txn.patient_contact (
    patient_id    uuid        not null references txn.patient(patient_id) on delete cascade,
    priority      smallint    not null,              -- 1 = call first
    contact_name  text        not null,
    relationship  text        not null,
    phone_e164    text        not null,
    created_at    timestamptz not null default now(),

    primary key (patient_id, priority),
    constraint contact_priority_range     check (priority between 1 and 3),
    constraint contact_relationship_known check (relationship in
        ('spouse','son','daughter','sibling','parent','other_family','friend','caregiver')),
    constraint contact_phone_e164         check (phone_e164 ~ '^\+[1-9][0-9]{7,14}$')
);


-- 3. Preferred check-in window -------------------------------------------
alter table txn.patient_episode
    add column checkin_window_start time not null default '08:00',
    add column checkin_window_end   time not null default '10:00',
    add constraint episode_checkin_window_ordered check (checkin_window_end > checkin_window_start);


-- 4. Consent decisions ---------------------------------------------------
alter table meta.hospital
    add column privacy_law text not null default 'DPDP-2023',
    add constraint hospital_privacy_law_known check (privacy_law in ('DPDP-2023','HIPAA'));

create table txn.episode_consent (
    episode_id    uuid        not null references txn.patient_episode(episode_id) on delete cascade,
    consent_code  text        not null,
    granted       boolean     not null,
    privacy_law   text        not null,
    form_version  text        not null,
    recorded_by   uuid        references meta.admin_user(admin_user_id) on delete set null,
    recorded_at   timestamptz not null default now(),

    primary key (episode_id, consent_code),
    constraint consent_code_known
        check (consent_code in ('remote_monitoring','data_processing','contact_sharing')),
    constraint consent_privacy_law_known
        check (privacy_law in ('DPDP-2023','HIPAA'))
);


-- 5. Baseline-only measures and LOINC codes ------------------------------
alter table meta.parameter add column loinc_code text;

insert into meta.parameter
    (parameter_code, parameter_name, parameter_type, unit,
     value_min, value_max, decimal_places, concerning_when_true)
values
    ('height_cm', 'Height',                    'numeric', 'cm',   100, 230, 0, null),
    ('weight_kg', 'Weight',                    'numeric', 'kg',    25, 250, 1, null),
    ('bp_sys',    'Blood pressure, systolic',  'numeric', 'mmHg',  60, 260, 0, null),
    ('bp_dia',    'Blood pressure, diastolic', 'numeric', 'mmHg',  30, 160, 0, null)
on conflict (parameter_code) do nothing;

update meta.parameter p
   set loinc_code = v.loinc
  from (values ('temp_c',   '8310-5'),  ('hr',        '8867-4'),  ('spo2',   '59408-5'),
               ('pain',     '72514-3'), ('steps',     '55423-8'), ('height_cm', '8302-2'),
               ('weight_kg','29463-7'), ('bp_sys',    '8480-6'),  ('bp_dia',  '8462-4')) as v(code, loinc)
 where p.parameter_code = v.code;


-- 6. Grants and row-level security ---------------------------------------
-- A returning patient's details are refreshed when they are re-enrolled.
grant update (phone_e164, language_code, date_of_birth, gender,
              address_line, address_city, address_district, address_state, address_postal_code,
              alt_phone_e164, email)
    on txn.patient to eras_app;
grant select, insert, delete on txn.patient_contact to eras_app;
grant select, insert on txn.episode_consent to eras_app;

alter table txn.patient_contact enable row level security;
alter table txn.episode_consent enable row level security;

create policy tenant_isolation on txn.patient_contact to eras_app
    using (patient_id in (select patient_id from txn.patient
                          where hospital_id = meta.current_hospital_id()));

create policy tenant_isolation on txn.episode_consent to eras_app
    using (episode_id in (select episode_id from txn.patient_episode
                          where hospital_id = meta.current_hospital_id()));
