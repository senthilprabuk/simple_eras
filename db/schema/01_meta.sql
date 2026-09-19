-- =====================================================================
--  meta — reference entities and clinical rules (slow-changing)
--
--  Build a fresh database by running, in order:
--    db/schema/01_meta.sql
--    db/schema/02_txn.sql
--    db/schema/03_views.sql
--    db/schema/04_security.sql
--    db/seed/01_reference.sql
--    db/seed/02_fixtures.sql        (optional: synthetic test patients)
--
--  This is the current shape of the schema, including the effect of every
--  file in db/migrations/. 04_security.sql records those migrations in
--  meta.schema_migration, so db/migrate.py never re-runs them here.
--  Migration 001 drops and re-adds the attribution columns, so running it
--  by hand against these tables would erase their data.
-- =====================================================================

begin;

create schema if not exists meta;
create schema if not exists txn;

-- gen_random_uuid() is built into PostgreSQL 13+, so no pgcrypto needed.


-- ---------------------------------------------------------------------
-- schema_migration   (which files in db/migrations/ have been applied)
-- ---------------------------------------------------------------------
create table meta.schema_migration (
    version     text        primary key,       -- file prefix, e.g. '003'
    name        text        not null,
    applied_at  timestamptz not null default now()
);


-- ---------------------------------------------------------------------
-- shared: updated_at trigger
-- ---------------------------------------------------------------------
create or replace function meta.set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;


-- ---------------------------------------------------------------------
-- hospital
-- ---------------------------------------------------------------------
create table meta.hospital (
    hospital_id       integer generated always as identity primary key,
    hospital_code     text        not null unique,          -- short stable key, e.g. 'CBE-01'
    hospital_name     text        not null,
    city              text,
    timezone          text        not null default 'Asia/Kolkata',
    ack_window_secs   integer     not null default 900,     -- escalation timer, per hospital
    is_active         boolean     not null default true,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint hospital_ack_window_sane
        check (ack_window_secs between 60 and 7200)
);

create trigger hospital_touch before update on meta.hospital
    for each row execute function meta.set_updated_at();


-- ---------------------------------------------------------------------
-- admin_user   (hospital-scoped clinician and admin accounts)
--   Email is unique per hospital, not globally: the same clinician may
--   hold accounts at two hospitals, and login disambiguates on hospital_id.
-- ---------------------------------------------------------------------
create table meta.admin_user (
    admin_user_id     uuid        primary key default gen_random_uuid(),
    hospital_id       integer     not null references meta.hospital(hospital_id) on delete restrict,
    email             text        not null,
    hashed_password   text        not null,
    full_name         text        not null,
    role              text        not null default 'admin',
    is_active         boolean     not null default true,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint admin_user_role_known
        check (role in ('admin', 'superadmin')),
    -- stored lowercase so the unique constraint below is case-insensitive
    constraint admin_user_email_lowercase
        check (email = lower(email)),
    constraint admin_user_hospital_email_unique
        unique (hospital_id, email)
);

create index admin_user_email_idx on meta.admin_user (email);

create trigger admin_user_touch before update on meta.admin_user
    for each row execute function meta.set_updated_at();


-- ---------------------------------------------------------------------
-- surgical_procedure
--   NOTE: "procedure" is a RESERVED keyword in PostgreSQL. A table named
--   procedure must be double-quoted at every single reference forever.
--   Renamed to surgical_procedure.
-- ---------------------------------------------------------------------
create table meta.surgical_procedure (
    procedure_id      integer generated always as identity primary key,
    procedure_code    text        not null unique,          -- 'TKR', 'THR'
    procedure_name    text        not null,
    procedure_desc    text,
    observation_days  smallint    not null,
    is_active         boolean     not null default true,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint procedure_observation_days_sane
        check (observation_days between 1 and 365)
);

create trigger procedure_touch before update on meta.surgical_procedure
    for each row execute function meta.set_updated_at();


-- ---------------------------------------------------------------------
-- hospital_procedure   (which hospital offers which procedure)
--   No hospital_name here: it would duplicate meta.hospital and drift the
--   first time a hospital is renamed. Join for it instead.
-- ---------------------------------------------------------------------
create table meta.hospital_procedure (
    hospital_id   integer not null references meta.hospital(hospital_id)            on delete cascade,
    procedure_id  integer not null references meta.surgical_procedure(procedure_id) on delete restrict,
    enabled_on    date    not null default current_date,
    is_active     boolean not null default true,

    primary key (hospital_id, procedure_id)
);


-- ---------------------------------------------------------------------
-- parameter   (the registry of things that can be tracked)
--   Typed min/max columns so the database can enforce ranges; ordinal
--   values live in parameter_option below.
-- ---------------------------------------------------------------------
create table meta.parameter (
    parameter_id         integer generated always as identity primary key,
    parameter_code       text        not null unique,   -- 'temp_c', 'calf_pain', 'knee_bend'
    parameter_name       text        not null,          -- 'Temperature'
    parameter_desc       text,
    parameter_type       text        not null,          -- numeric | boolean | ordinal
    unit                 text,                          -- 'C', 'bpm', '%', null for boolean
    value_min            numeric(10,2),                 -- numeric types only
    value_max            numeric(10,2),
    decimal_places       smallint    not null default 0,
    concerning_when_true boolean,                       -- booleans: which answer is the worrying one
    is_active            boolean     not null default true,
    created_at           timestamptz not null default now(),

    constraint parameter_type_known
        check (parameter_type in ('numeric','boolean','ordinal')),
    constraint parameter_range_ordered
        check (value_min is null or value_max is null or value_min <= value_max),
    constraint parameter_numeric_needs_range
        check (parameter_type <> 'numeric'
               or (value_min is not null and value_max is not null)),
    constraint parameter_boolean_needs_polarity
        check (parameter_type <> 'boolean' or concerning_when_true is not null)
);


-- ---------------------------------------------------------------------
-- parameter_option   (valid values for ordinal parameters)
--   ordinal_rank is what makes 'walker < crutches < cane < none'
--   comparable, which a comma-separated string could never do.
-- ---------------------------------------------------------------------
create table meta.parameter_option (
    parameter_id  integer  not null references meta.parameter(parameter_id) on delete cascade,
    option_code   text     not null,          -- 'chair', 'car', 'bike'
    option_label  text     not null,          -- 'Sit in a dining chair'
    ordinal_rank  smallint not null,          -- 1, 2, 3 — higher is better progress

    primary key (parameter_id, option_code),
    unique (parameter_id, ordinal_rank)
);


-- ---------------------------------------------------------------------
-- ruleset   (the version wrapper around scoring)
--   Weights and bands change when a surgeon revises them. If they hang
--   straight off procedure_id, editing a weight silently rewrites the
--   reasoning behind every past alert. Versioning makes decisions
--   reconstructable, which is the first thing asked for when a clinician
--   disputes an alert.
-- ---------------------------------------------------------------------
create table meta.ruleset (
    ruleset_id               integer generated always as identity primary key,
    procedure_id             integer     not null references meta.surgical_procedure(procedure_id),
    version                  text        not null,              -- '1.0.0'
    review_at                smallint    not null,              -- weighted-total cutoffs
    critical_at              smallint    not null,
    max_points_per_parameter smallint    not null default 6,
    status                   text        not null default 'draft',
    approved_by              text,
    approved_at              timestamptz,
    notes                    text,
    created_at               timestamptz not null default now(),

    unique (procedure_id, version),
    constraint ruleset_status_known
        check (status in ('draft','approved','retired')),
    constraint ruleset_tiers_ordered
        check (critical_at > review_at and review_at > 0),
    constraint ruleset_approved_has_approver
        check (status <> 'approved'
               or (approved_by is not null and approved_at is not null))
);

-- at most one approved ruleset per procedure at any time
create unique index ruleset_one_approved_per_procedure
    on meta.ruleset (procedure_id)
    where status = 'approved';


-- ---------------------------------------------------------------------
-- procedure_parameter   (binds parameters to a ruleset)
--   Two windows, deliberately decoupled:
--     collect_from_day / collect_to_day  -> what the form ASKS
--     score_from_day   / score_to_day    -> what the engine SCORES
--
--   Duration of wound drainage is itself the predictor, so the question is
--   asked from day 0 while the signal only counts from day 5. Hiding the
--   question until day 5 would throw away the very thing that matters.
--
--   scoring_config is jsonb, not YAML text. Authors can still write YAML;
--   the loader converts. jsonb is queryable, validatable and indexable.
-- ---------------------------------------------------------------------
create table meta.procedure_parameter (
    ruleset_id       integer  not null references meta.ruleset(ruleset_id)      on delete cascade,
    parameter_id     integer  not null references meta.parameter(parameter_id)  on delete restrict,
    display_order    smallint not null,
    display_section  text     not null default 'readings',   -- readings | checks | progress
    collect_from_day smallint not null default 0,
    collect_to_day   smallint not null,
    score_from_day   smallint not null,
    score_to_day     smallint not null,
    is_mandatory     boolean  not null default false,
    parameter_weight smallint not null,
    scoring_config   jsonb    not null,        -- bands / bands_by_day / binary_score / detector
    question_text    text,                     -- patient-facing wording
    nurse_script     text,                     -- what to ask when this rule fires

    primary key (ruleset_id, parameter_id),
    unique (ruleset_id, display_order),
    constraint ppm_window_ordered   check (collect_to_day >= collect_from_day),
    constraint ppm_window_sane      check (collect_from_day >= 0 and collect_to_day <= 365),
    constraint ppm_weight_sane      check (parameter_weight between 0 and 10),
    constraint ppm_section_known    check (display_section in ('readings','checks','progress')),
    constraint ppm_scoring_is_object check (jsonb_typeof(scoring_config) = 'object'),
    constraint ppm_score_window_ordered
        check (score_to_day >= score_from_day),
    -- you can never score something you do not collect
    constraint ppm_score_within_collect
        check (score_from_day >= collect_from_day
           and score_to_day   <= collect_to_day)
);

create index procedure_parameter_by_param on meta.procedure_parameter (parameter_id);

commit;
