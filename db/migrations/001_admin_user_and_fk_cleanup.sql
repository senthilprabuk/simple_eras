-- =====================================================================
-- Migration: 001_admin_user_and_fk_cleanup.sql
-- Purpose:
--   1. Create meta.admin_user table for hospital-scoped admin auth
--   2. Evolve txn.alert:
--        - Drop escalated_to (escalation notifies all active admins at hospital)
--        - Convert acknowledged_by from text to uuid FK -> meta.admin_user
--        - Convert resolved_by from text to uuid FK -> meta.admin_user
--   3. Evolve txn.patient_episode:
--        - Convert enrolled_by from text to uuid FK -> meta.admin_user
--   4. Extend txn.v_alert_queue view:
--        - Add hospital_id for multi-tenant query filtering
--        - Add acknowledged boolean, acknowledged_at, acknowledged_by_name
--        - Add patient_id, mrn, procedure_code
--
-- WARNING: destructive. It drops and re-adds acknowledged_by, resolved_by
-- and enrolled_by, discarding their contents. Apply it only through
-- db/migrate.py, which records it and never runs it twice.
-- =====================================================================

BEGIN;

-- 1. Drop existing view first so underlying table columns can be altered cleanly
DROP VIEW IF EXISTS txn.v_alert_queue;

-- 2. Create the meta.admin_user table
CREATE TABLE IF NOT EXISTS meta.admin_user (
    admin_user_id     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    hospital_id       integer     NOT NULL REFERENCES meta.hospital(hospital_id) ON DELETE RESTRICT,
    email             text        NOT NULL,
    hashed_password   text        NOT NULL,
    full_name         text        NOT NULL,
    role              text        NOT NULL DEFAULT 'admin',
    is_active         boolean     NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT admin_user_role_known CHECK (role IN ('admin', 'superadmin')),
    CONSTRAINT admin_user_hospital_email_unique UNIQUE (hospital_id, email)
);

-- Fast lookup by email for login authentication
CREATE INDEX IF NOT EXISTS admin_user_email_idx ON meta.admin_user (email);

-- Automated updated_at trigger reuse
DROP TRIGGER IF EXISTS admin_user_touch ON meta.admin_user;
CREATE TRIGGER admin_user_touch BEFORE UPDATE ON meta.admin_user
    FOR EACH ROW EXECUTE FUNCTION meta.set_updated_at();

-- 3. Evolve txn.alert
-- Drop escalated_to
ALTER TABLE txn.alert DROP COLUMN IF EXISTS escalated_to;

-- Replace text columns with UUID foreign keys
ALTER TABLE txn.alert DROP COLUMN IF EXISTS acknowledged_by;
ALTER TABLE txn.alert ADD COLUMN acknowledged_by uuid REFERENCES meta.admin_user(admin_user_id) ON DELETE SET NULL;

ALTER TABLE txn.alert DROP COLUMN IF EXISTS resolved_by;
ALTER TABLE txn.alert ADD COLUMN resolved_by uuid REFERENCES meta.admin_user(admin_user_id) ON DELETE SET NULL;

-- 4. Evolve txn.patient_episode
-- Convert enrolled_by to UUID FK
ALTER TABLE txn.patient_episode DROP COLUMN IF EXISTS enrolled_by;
ALTER TABLE txn.patient_episode ADD COLUMN enrolled_by uuid REFERENCES meta.admin_user(admin_user_id) ON DELETE SET NULL;

-- 5. Recreate txn.v_alert_queue with hospital_id and acknowledgement metadata
CREATE OR REPLACE VIEW txn.v_alert_queue AS
SELECT 
    a.alert_id,
    a.tier,
    a.status,
    a.raised_at,
    (EXTRACT(epoch FROM (now() - a.raised_at)))::integer AS age_secs,
    (a.acknowledged_at IS NOT NULL) AS acknowledged,
    a.acknowledged_at,
    a.acknowledged_by,
    au.full_name AS acknowledged_by_name,
    pt.patient_id,
    pt.patient_name,
    pt.mrn,
    e.episode_id,
    e.hospital_id,
    h.hospital_name,
    sp.procedure_code,
    ev.day_after_discharge,
    ev.reasons
FROM txn.alert a
JOIN txn.check_in_evaluation ev ON ev.evaluation_id = a.evaluation_id
JOIN txn.patient_episode e      ON e.episode_id = a.episode_id
JOIN txn.patient pt             ON pt.patient_id = e.patient_id
JOIN meta.hospital h            ON h.hospital_id = e.hospital_id
JOIN meta.surgical_procedure sp ON sp.procedure_id = e.procedure_id
LEFT JOIN meta.admin_user au     ON au.admin_user_id = a.acknowledged_by
WHERE a.status IN ('open', 'acknowledged')
ORDER BY
    CASE a.tier 
        WHEN 'emergency' THEN 1 
        WHEN 'critical'  THEN 2 
        WHEN 'review'    THEN 3 
        WHEN 'missed'    THEN 4 
        ELSE 5 
    END,
    a.raised_at ASC;

COMMIT;
