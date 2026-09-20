-- =====================================================================
-- Migration: 011_patient_messages.sql
-- Purpose:
--   Patient message audit and delivery log for WhatsApp check-ins.
--   Supports Option A: Hybrid Magic-Link Method.
-- =====================================================================

-- Allow checkin_confirmation template
alter table meta.message_template drop constraint if exists template_key_known;
alter table meta.message_template add constraint template_key_known
    check (template_key in ('enrollment_welcome', 'checkin_reminder', 'missed_checkin', 'urgent_guidance', 'checkin_confirmation'));

-- Seed default checkin_confirmation template for active hospitals
insert into meta.message_template (hospital_id, template_key, language_code, body)
select h.hospital_id, 'checkin_confirmation', 'en',
       'Thank you {patient_first_name}. Your Day {post_op_day} check-in has been received and your recovery is on track. Keep up with your exercises.'
from meta.hospital h
on conflict do nothing;

-- ---------------------------------------------------------------------
-- txn.patient_message
-- ---------------------------------------------------------------------
create table if not exists txn.patient_message (
    message_id           uuid        primary key default gen_random_uuid(),
    episode_id           uuid        not null references txn.patient_episode(episode_id) on delete cascade,
    patient_id           uuid        not null references txn.patient(patient_id),
    hospital_id          integer     not null references meta.hospital(hospital_id),
    message_type         text        not null,
    day_after_discharge  integer     not null,
    phone_e164           text        not null,
    channel              text        not null default 'whatsapp',
    direction            text        not null default 'outbound',
    body                 text        not null,
    magic_token          text,
    magic_url            text,
    meta_message_id      text,
    status               text        not null default 'queued',
    error_message        text,
    sent_at              timestamptz,
    delivered_at         timestamptz,
    read_at              timestamptz,
    created_at           timestamptz not null default now(),

    constraint patient_message_type_known
        check (message_type in ('checkin_reminder', 'checkin_confirmation', 'urgent_guidance', 'missed_checkin', 'followup_nudge', 'inbound')),
    constraint patient_message_channel_known
        check (channel in ('whatsapp', 'sms')),
    constraint patient_message_direction_known
        check (direction in ('outbound', 'inbound')),
    constraint patient_message_status_known
        check (status in ('queued', 'sent', 'delivered', 'read', 'failed'))
);

-- Guarantee idempotency: at most one checkin reminder per episode per post-op day
create unique index if not exists patient_message_unique_daily_reminder
    on txn.patient_message (episode_id, day_after_discharge, message_type)
    where message_type = 'checkin_reminder';

create index if not exists patient_message_by_meta_id
    on txn.patient_message (meta_message_id)
    where meta_message_id is not null;

create index if not exists patient_message_by_episode
    on txn.patient_message (episode_id, created_at desc);

-- Security and row level security
alter table txn.patient_message enable row level security;

drop policy if exists tenant_isolation on txn.patient_message;
create policy tenant_isolation on txn.patient_message to eras_app
    using (hospital_id = meta.current_hospital_id());

grant select, insert, update on txn.patient_message to eras_app;
