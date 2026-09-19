-- =====================================================================
-- Migration: 005_admin_screens.sql
-- Purpose:
--   Support the clinician screens beyond the dashboard.
--   1. meta.message_template: per-hospital WhatsApp wording, one row per
--      template and language. Seeded with English defaults for every
--      existing hospital; Tamil and Hindi are left for the hospital to
--      write rather than machine-translating clinical guidance.
--   2. Row-level security on the hospital-owned meta tables, so a tenant
--      session can read and change only its own hospital's settings,
--      procedures and templates.
--   3. Grants for enrollment (insert patient, episode, baseline), hospital
--      settings, and template editing.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

create table meta.message_template (
    hospital_id    integer     not null references meta.hospital(hospital_id) on delete cascade,
    template_key   text        not null,
    language_code  text        not null,
    body           text        not null,
    is_active      boolean     not null default true,
    updated_at     timestamptz not null default now(),
    updated_by     uuid        references meta.admin_user(admin_user_id) on delete set null,

    primary key (hospital_id, template_key, language_code),
    constraint template_key_known
        check (template_key in ('enrollment_welcome', 'checkin_reminder', 'missed_checkin', 'urgent_guidance')),
    constraint template_language_known
        check (language_code in ('en', 'ta', 'hi')),
    -- WhatsApp's limit for a template body
    constraint template_body_length
        check (char_length(body) between 1 and 1024)
);

create trigger message_template_touch before update on meta.message_template
    for each row execute function meta.set_updated_at();

insert into meta.message_template (hospital_id, template_key, language_code, body)
select h.hospital_id, t.template_key, 'en', t.body
from meta.hospital h
cross join (values
    ('enrollment_welcome',
     'Hello {patient_first_name}, this is {hospital_name}. While you recover from your knee surgery we will send you a short daily check-in here. It takes about two minutes.'),
    ('checkin_reminder',
     'Good morning {patient_first_name}. It is day {post_op_day} after your surgery. Please complete today''s check-in: {checkin_link}'),
    ('missed_checkin',
     'Hello {patient_first_name}, we have not received your check-in yet. Please complete it now so {hospital_name} can follow your recovery: {checkin_link}'),
    ('urgent_guidance',
     '{patient_first_name}, you reported a symptom that needs attention today. Please call {hospital_name} now. If you have chest pain or severe breathlessness, call emergency services immediately.')
) as t(template_key, body)
on conflict do nothing;

alter table meta.hospital           enable row level security;
alter table meta.hospital_procedure enable row level security;
alter table meta.message_template   enable row level security;

drop policy if exists tenant_isolation on meta.hospital;
create policy tenant_isolation on meta.hospital to eras_app
    using (hospital_id = meta.current_hospital_id());

drop policy if exists tenant_isolation on meta.hospital_procedure;
create policy tenant_isolation on meta.hospital_procedure to eras_app
    using (hospital_id = meta.current_hospital_id());

drop policy if exists tenant_isolation on meta.message_template;
create policy tenant_isolation on meta.message_template to eras_app
    using (hospital_id = meta.current_hospital_id());

grant update (hospital_name, city, timezone, ack_window_secs) on meta.hospital to eras_app;
grant select, insert, update on meta.message_template to eras_app;
grant insert on txn.patient, txn.patient_episode, txn.episode_baseline to eras_app;
