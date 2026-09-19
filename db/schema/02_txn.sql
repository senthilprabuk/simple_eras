-- =====================================================================
--  txn — patient data, check-ins, evaluations and alerts (fast-growing)
--
--  Requires: 01_meta.sql
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- patient   (the person — stable across surgeries)
-- ---------------------------------------------------------------------
create table txn.patient (
    patient_id    uuid        primary key default gen_random_uuid(),
    hospital_id   integer     not null references meta.hospital(hospital_id),
    mrn           text,                                   -- hospital record number, typed in manually
    patient_name  text        not null,
    phone_e164    text        not null,
    language_code text        not null default 'en',
    date_of_birth date,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),

    unique (hospital_id, mrn),
    -- target for patient_episode's same-hospital foreign key
    constraint patient_id_hospital_unique unique (patient_id, hospital_id),
    constraint patient_language_known check (language_code in ('en','ta','hi')),
    constraint patient_phone_e164     check (phone_e164 ~ '^\+[1-9][0-9]{7,14}$')
);

create trigger patient_touch before update on txn.patient
    for each row execute function meta.set_updated_at();


-- ---------------------------------------------------------------------
-- patient_episode   (one monitored recovery)
--   Gives discharge_date a home — without it day_after_discharge cannot
--   be validated or recomputed — and lets a patient have a second surgery
--   later without corrupting the first episode's history.
-- ---------------------------------------------------------------------
create table txn.patient_episode (
    episode_id         uuid        primary key default gen_random_uuid(),
    patient_id         uuid        not null references txn.patient(patient_id)             on delete restrict,
    hospital_id        integer     not null references meta.hospital(hospital_id),
    procedure_id       integer     not null references meta.surgical_procedure(procedure_id),
    ruleset_id         integer     not null references meta.ruleset(ruleset_id),
    surgery_date       date        not null,
    discharge_date     date        not null,
    monitoring_ends_on date        not null,
    consent_version    text        not null,
    consent_at         timestamptz not null,
    enrolled_by        uuid        references meta.admin_user(admin_user_id) on delete set null,
    status             text        not null default 'active',
    created_at         timestamptz not null default now(),

    constraint episode_status_known    check (status in ('active','completed','withdrawn')),
    constraint episode_dates_ordered   check (discharge_date >= surgery_date),
    constraint episode_end_after_disch check (monitoring_ends_on > discharge_date),
    -- an episode may only belong to its patient's own hospital, so the
    -- tenant a query filters on can never disagree between the two tables
    constraint episode_patient_same_hospital
        foreign key (patient_id, hospital_id) references txn.patient (patient_id, hospital_id)
);

-- a patient cannot be in two active monitoring programmes at once
create unique index episode_one_active_per_patient
    on txn.patient_episode (patient_id)
    where status = 'active';

create index episode_active_by_hospital
    on txn.patient_episode (hospital_id, status);


-- ---------------------------------------------------------------------
-- episode_baseline   (discharge readings — the comparison anchor)
-- ---------------------------------------------------------------------
create table txn.episode_baseline (
    episode_id   uuid        not null references txn.patient_episode(episode_id) on delete cascade,
    parameter_id integer     not null references meta.parameter(parameter_id),
    value_num    numeric(10,2),
    value_bool   boolean,
    value_code   text,
    recorded_at  timestamptz not null default now(),

    primary key (episode_id, parameter_id),
    constraint baseline_exactly_one_value check (
        (value_num  is not null)::int
      + (value_bool is not null)::int
      + (value_code is not null)::int = 1)
);


-- ---------------------------------------------------------------------
-- patient_check_in   (the submission header)
--   Header here, values in the child table below. A single table mixing
--   fixed vital columns with an EAV pair would repeat the vitals on every
--   parameter row, and would defeat the parameter registry: adding a
--   parameter would need a schema change.
-- ---------------------------------------------------------------------
create table txn.patient_check_in (
    check_in_id         uuid        primary key default gen_random_uuid(),
    episode_id          uuid        not null references txn.patient_episode(episode_id) on delete cascade,
    day_after_discharge smallint    not null,
    submitted_at        timestamptz not null default now(),
    captured_at         timestamptz,                    -- set on device; survives the offline queue
    source              text        not null default 'patient',
    idempotency_key     text,                           -- stops offline replay creating duplicates
    photo_key           text,                           -- object storage key, never a URL
    is_superseded       boolean     not null default false,

    constraint checkin_day_sane   check (day_after_discharge between 0 and 365),
    constraint checkin_source_known
        check (source in ('patient','proxy','nurse','synthetic'))
);

create unique index check_in_idempotency
    on txn.patient_check_in (episode_id, idempotency_key)
    where idempotency_key is not null;

-- drives "latest submission for this day"
create index check_in_by_day
    on txn.patient_check_in (episode_id, day_after_discharge, submitted_at desc);


-- ---------------------------------------------------------------------
-- patient_check_in_value   (one row per answered parameter)
--   A parameter with NO ROW here was not answered. That is deliberate and
--   load-bearing: the engine must distinguish "unknown" from "normal",
--   and a nullable wide column cannot express that difference.
-- ---------------------------------------------------------------------
create table txn.patient_check_in_value (
    check_in_id  uuid    not null references txn.patient_check_in(check_in_id) on delete cascade,
    parameter_id integer not null references meta.parameter(parameter_id)      on delete restrict,
    value_num    numeric(10,2),
    value_bool   boolean,
    value_code   text,

    primary key (check_in_id, parameter_id),
    constraint value_exactly_one check (
        (value_num  is not null)::int
      + (value_bool is not null)::int
      + (value_code is not null)::int = 1)
);

create index check_in_value_by_param on txn.patient_check_in_value (parameter_id);


-- ---------------------------------------------------------------------
-- check_in_evaluation   (what the rules engine decided)
--   check_in_id is nullable on purpose: a missed check-in is evaluated
--   against a synthetic empty reading and still produces a row.
-- ---------------------------------------------------------------------
create table txn.check_in_evaluation (
    evaluation_id       uuid        primary key default gen_random_uuid(),
    check_in_id         uuid        references txn.patient_check_in(check_in_id)        on delete cascade,
    episode_id          uuid        not null references txn.patient_episode(episode_id) on delete cascade,
    ruleset_id          integer     not null references meta.ruleset(ruleset_id),
    day_after_discharge smallint    not null,
    tier                text        not null,
    total_score         smallint,
    is_override         boolean     not null default false,
    reasons             jsonb       not null default '[]'::jsonb,
    reason_key          text        not null,      -- hash of sorted reason names, drives dedup
    coverage            numeric(4,3),              -- fraction of expected parameters answered
    evaluated_at        timestamptz not null default now(),

    constraint eval_tier_known
        check (tier in ('normal','review','critical','emergency','missed')),
    constraint eval_coverage_fraction
        check (coverage is null or coverage between 0 and 1),
    constraint eval_reasons_is_array
        check (jsonb_typeof(reasons) = 'array')
);

create index evaluation_timeline
    on txn.check_in_evaluation (episode_id, day_after_discharge, evaluated_at desc);


-- ---------------------------------------------------------------------
-- alert
--   acknowledged_by and resolved_by are foreign keys into meta.admin_user,
--   so attribution survives a clinician being renamed. There is no
--   escalated_to: escalation notifies every active admin at the hospital.
-- ---------------------------------------------------------------------
create table txn.alert (
    alert_id        uuid        primary key default gen_random_uuid(),
    episode_id      uuid        not null references txn.patient_episode(episode_id)      on delete cascade,
    evaluation_id   uuid        not null references txn.check_in_evaluation(evaluation_id),
    tier            text        not null,
    reason_key      text        not null,
    status          text        not null default 'open',
    raised_at       timestamptz not null default now(),
    notified_at     timestamptz,
    acknowledged_at timestamptz,
    acknowledged_by uuid        references meta.admin_user(admin_user_id) on delete set null,
    escalated_at    timestamptz,
    resolved_at     timestamptz,
    resolved_by     uuid        references meta.admin_user(admin_user_id) on delete set null,
    outcome         text,
    outcome_note    text,

    constraint alert_tier_known
        check (tier in ('review','critical','emergency','missed')),
    constraint alert_status_known
        check (status in ('open','acknowledged','resolved','expired')),
    constraint alert_outcome_known
        check (outcome is null or outcome in
               ('reassured','plan_adjusted','same_day_review','emergency')),
    -- there is no "dismiss": every resolved alert carries an outcome
    constraint alert_resolved_needs_outcome
        check (status <> 'resolved'
               or (outcome is not null and resolved_at is not null)),
    constraint alert_ack_before_resolve
        check (resolved_at is null or acknowledged_at is null
               or resolved_at >= acknowledged_at)
);

-- deduplication: only one live alert per reason set per episode
create unique index alert_one_live_per_reason
    on txn.alert (episode_id, reason_key)
    where status in ('open','acknowledged');

-- the nurse queue
create index alert_queue
    on txn.alert (status, tier, raised_at)
    where status in ('open','acknowledged');

-- the escalation sweep, run every 60s
create index alert_escalation_sweep
    on txn.alert (notified_at)
    where status = 'open' and tier in ('critical','emergency');


-- ---------------------------------------------------------------------
-- alert_notification   (delivery attempts — push, SMS and email)
-- ---------------------------------------------------------------------
create table txn.alert_notification (
    notification_id uuid        primary key default gen_random_uuid(),
    alert_id        uuid        not null references txn.alert(alert_id) on delete cascade,
    recipient       text        not null,
    channel         text        not null,
    provider_ref    text,
    status          text        not null default 'queued',
    attempts        smallint    not null default 0,
    last_error      text,
    sent_at         timestamptz,
    created_at      timestamptz not null default now(),

    constraint notif_channel_known check (channel in ('push','sms','email')),
    constraint notif_status_known  check (status in ('queued','sent','failed'))
);

create index notification_by_alert on txn.alert_notification (alert_id);

-- the notification dispatcher's work queue
create index notification_queued
    on txn.alert_notification (created_at)
    where status = 'queued';

commit;
