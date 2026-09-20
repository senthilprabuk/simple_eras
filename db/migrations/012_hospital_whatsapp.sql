-- =====================================================================
-- Migration: 012_hospital_whatsapp.sql
-- Purpose:
--   Hospital WhatsApp Business Account management and credentials.
--   Enables in-app Settings configuration and QR code generation.
-- =====================================================================

create table if not exists meta.hospital_whatsapp (
    account_id           uuid        primary key default gen_random_uuid(),
    hospital_id          integer     not null references meta.hospital(hospital_id) on delete cascade,
    display_name         text        not null,
    display_phone_number text        not null,
    phone_number_id      text        not null unique,
    waba_id              text        not null,
    access_token         text        not null,
    verify_token         text        not null,
    meta_app_id          text,
    health_status        text        not null default 'healthy',
    is_default           boolean     not null default true,
    is_active            boolean     not null default true,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),

    constraint hospital_whatsapp_health_known
        check (health_status in ('healthy', 'invalid_token', 'rate_limited', 'unverified'))
);

create unique index if not exists idx_hospital_whatsapp_one_default
    on meta.hospital_whatsapp (hospital_id)
    where is_default = true;

grant select, insert, update, delete on meta.hospital_whatsapp to eras_app;

alter table meta.hospital_whatsapp enable row level security;

drop policy if exists tenant_isolation on meta.hospital_whatsapp;
create policy tenant_isolation on meta.hospital_whatsapp to eras_app
    using (hospital_id = meta.current_hospital_id());

-- Seed default demo WhatsApp business account for St. Mary's Orthopedic Center (CBE-01)
insert into meta.hospital_whatsapp (
    hospital_id, display_name, display_phone_number,
    phone_number_id, waba_id, access_token, verify_token,
    health_status, is_default, is_active
)
select
    h.hospital_id,
    'St. Mary''s Orthopedic Helpline',
    '+91 98765 43210',
    '104239857123456',
    '108374829103948',
    'mock_meta_access_token_stmarys',
    'eras_stmarys_verify_2026',
    'healthy',
    true,
    true
from meta.hospital h
where h.hospital_code = 'CBE-01'
on conflict (phone_number_id) do nothing;
