-- =====================================================================
--  Fixture patients — 12 synthetic recovery timelines
--
--  Each fixture exercises one behaviour of the rules engine: a control
--  that must never escalate, a slow-burn infection, a DVT override, a PE
--  emergency, a drop-out, and so on. Expected outcomes are written to
--  txn.fixture_expectation for the Python harness to assert against.
--
--  Requires: db/schema/*.sql, db/seed/01_reference.sql
--
--  Deterministic and re-runnable: noise is hash-derived rather than
--  random(), and every run deletes and rebuilds the FX-* patients.
--  Dates are anchored to today in the hospital's own timezone — the same
--  calendar the API uses for post-op day — so each run places the fixtures
--  at day 21. Re-run it to reset them after the calendar has moved on.
--
--  Re-running removes the fixture episodes, which cascades to their
--  evaluations and alerts. Re-run backend/seed/seed_demo.py afterwards
--  if you need the demo alerts back.
--
--  12 patients, 237 check-ins. Fixture codes are stable identifiers, so
--  the retired f10 leaves a gap in the FX- numbering rather than
--  renumbering the fixtures after it.
--  Verify the load with db/seed/verify_fixtures.sql.
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- 1. Deterministic noise (hash-derived, not random())
-- ---------------------------------------------------------------------
create or replace function txn.fx_noise(seed text, amp numeric)
returns numeric language sql immutable as $$
    select amp * (
        (abs((('x' || substr(md5(seed), 1, 8))::bit(32)::int)::bigint) % 2001) - 1000
    )::numeric / 1000.0;
$$;


-- ---------------------------------------------------------------------
-- 2. Staging
-- ---------------------------------------------------------------------
create temporary table fx_patient (
    fixture      text primary key,
    display_name text not null,
    last_day     smallint not null default 21,
    base_temp    numeric default 36.8,
    base_hr      int default 72,
    base_spo2    int default 97,
    base_pain    int default 6,
    purpose      text
) on commit drop;

create temporary table fx_curve (
    fixture        text,
    parameter_code text,
    day_from       int,
    day_to         int,
    start_val      numeric,
    end_val        numeric,
    noise          numeric default 0
) on commit drop;

create temporary table fx_discrete (
    fixture        text,
    parameter_code text,
    day_from       int,
    day_to         int,
    value_bool     boolean,
    value_code     text
) on commit drop;

create temporary table fx_gap (fixture text, day int) on commit drop;

-- "today" for the fixture hospital, in its own timezone
create temporary table fx_clock on commit drop as
select (now() at time zone h.timezone)::date as today, h.timezone
from meta.hospital h
where h.hospital_code = 'CBE-01';

-- submissions that did not come from the patient's own app
create temporary table fx_source (fixture text, day int, source text) on commit drop;

create temporary table fx_expect (
    fixture           text primary key,
    escalate_from     int,
    escalate_to       int,
    expect_tier       text,
    must_not_escalate boolean default false,
    expect_reasons    text[],
    note              text
) on commit drop;


-- ---------------------------------------------------------------------
-- 3. The twelve fixtures
--    Names are invented; the bracketed part names the scenario each tests.
-- ---------------------------------------------------------------------
insert into fx_patient (fixture, display_name, last_day, base_hr, purpose) values
 ('f01_smooth',        'Lakshmi Narayanan [Smooth Recovery]', 21, 72, 'Control. Must never escalate.'),
 ('f02_slow_burn',     'Rajesh Kumar [Slow Burn]',            21, 72, 'Infection from day 7. Arms fever_returned.'),
 ('f03_dvt',           'Meena Sundaram [Sudden Clot]',        21, 74, 'Binary override, day 4.'),
 ('f04_pe',            'Karthik Subramanian [Breathless]',    21, 76, 'Emergency override, day 6.'),
 ('f05_erratic',       'Priya Venkatesh [Erratic Reporter]',  21, 70, 'Gaps and noise, recovering.'),
 ('f06_dropout',       'Suresh Babu [Drop Out]',               5, 73, 'Stops day 5. Absence sweep.'),
 ('f07_combination',   'Kavitha Ramesh [Combination Creep]',  21, 70, 'No band 3. Weighted total escalates.'),
 ('f08_early_fever',   'Anand Krishnan [Early Low Fever]',    21, 80, 'Expected day 0-3 picture.'),
 ('f09_collect_score', 'Deepa Iyer [Collect Not Score]',      21, 72, 'Drainage from day 2: collected, scored from 5.'),
 ('f11_one_day_spike', 'Harish Patel [One Day Spike]',        21, 72, 'Hysteresis must hold the tier.'),
 ('f12_mobility_drop', 'Sunita Sharma [Mobility Drop]',       21, 72, 'Steps halve from personal best, day 12.'),
 ('f13_out_of_window', 'Ganesh Moorthy [Out Of Window]',      21, 72, 'Nurse enters knee_bend on day 5, outside collect.');

-- ---- who they are, where they live, and the first person to call
create temporary table fx_person (
    fixture       text primary key,
    gender        text,
    street        text,
    postal_code   text,
    contact_name  text,
    relationship  text
) on commit drop;

insert into fx_person values
 ('f01_smooth',        'female', '12 Race Course Road',            '641018', 'Arun Narayanan',   'son'),
 ('f02_slow_burn',     'male',   '45 Avinashi Road, Peelamedu',    '641004', 'Sangeetha Rajesh', 'spouse'),
 ('f03_dvt',           'female', '8 DB Road, RS Puram',            '641002', 'Vignesh Sundaram', 'son'),
 ('f04_pe',            'male',   '22 Sathy Road, Ganapathy',       '641006', 'Divya Karthik',    'spouse'),
 ('f05_erratic',       'female', '5 Trichy Road, Singanallur',     '641005', 'Venkatesh Rao',    'spouse'),
 ('f06_dropout',       'male',   '31 Mettupalayam Road',           '641043', 'Anitha Suresh',    'daughter'),
 ('f07_combination',   'female', '17 Cross Cut Road, Gandhipuram', '641012', 'Ramesh Kumar',     'spouse'),
 ('f08_early_fever',   'male',   '64 Saibaba Colony',              '641011', 'Revathi Anand',    'spouse'),
 ('f09_collect_score', 'female', '9 Thadagam Road',                '641025', 'Karthika Iyer',    'daughter'),
 ('f11_one_day_spike', 'male',   '3 Nanjundapuram Road',           '641036', 'Nisha Patel',      'daughter'),
 ('f12_mobility_drop', 'female', '27 Kalapatti Road',              '641048', 'Amit Sharma',      'son'),
 ('f13_out_of_window', 'male',   '11 Vadavalli Main Road',         '641041', 'Selvi Ganesh',     'spouse');

-- ---- numeric curves (spo2 runs to day 21, inside its collect window of 0-42)
insert into fx_curve (fixture, parameter_code, day_from, day_to, start_val, end_val, noise) values
 ('f01_smooth','temp_c', 0, 5, 37.4, 36.8, 0.12), ('f01_smooth','temp_c', 6,21, 36.8, 36.7, 0.12),
 ('f01_smooth','hr',     0,21, 88,   70,   3.0),
 ('f01_smooth','spo2',   0,21, 96,   98,   0.8),
 ('f01_smooth','pain',   0,10, 6,    2,    0.5), ('f01_smooth','pain',  11,21, 2,    1,    0.4),
 ('f01_smooth','steps',  0,21, 80,   1500, 60),

 ('f02_slow_burn','temp_c', 0, 3, 37.6, 36.9, 0.10), ('f02_slow_burn','temp_c', 4, 6, 36.9, 36.9, 0.08),
 ('f02_slow_burn','temp_c', 7,14, 37.0, 38.7, 0.12), ('f02_slow_burn','temp_c',15,21, 38.7, 38.9, 0.12),
 ('f02_slow_burn','hr',     0, 6, 86,   74,   3.0),  ('f02_slow_burn','hr',     7,21, 76,  108,   4.0),
 ('f02_slow_burn','spo2',   0,21, 96,   95,   0.9),
 ('f02_slow_burn','pain',   0, 5, 6,    3,    0.5),  ('f02_slow_burn','pain',   6,14, 3,    8,    0.6),
 ('f02_slow_burn','pain',  15,21, 8,    8,    0.5),
 ('f02_slow_burn','steps',  0, 8, 80,   600,  50),   ('f02_slow_burn','steps',  9,21, 600, 120,   40),

 ('f03_dvt','temp_c', 0, 5, 37.3, 36.9, 0.12), ('f03_dvt','temp_c', 6,21, 36.9, 36.8, 0.12),
 ('f03_dvt','hr',     0, 3, 86,   78,   3.0),  ('f03_dvt','hr',     4,21, 92,   88,   4.0),
 ('f03_dvt','spo2',   0,21, 96,   97,   0.8),
 ('f03_dvt','pain',   0,21, 6,    3,    0.6),
 ('f03_dvt','steps',  0,21, 90,   1100, 60),

 ('f04_pe','temp_c', 0,21, 37.2, 36.9, 0.12),
 ('f04_pe','hr',     0, 5, 84,   76,   3.0),  ('f04_pe','hr',     6,21, 104,  96,   4.0),
 ('f04_pe','spo2',   0, 5, 97,   96,   0.6),  ('f04_pe','spo2',   6,21, 89,   94,   1.0),
 ('f04_pe','pain',   0,21, 6,    3,    0.6),
 ('f04_pe','steps',  0,21, 85,   900,  60),

 ('f05_erratic','temp_c', 0,21, 37.3, 36.8, 0.28),
 ('f05_erratic','hr',     0,21, 86,   72,   8.0),
 ('f05_erratic','spo2',   0,21, 95,   98,   1.8),
 ('f05_erratic','pain',   0,21, 6,    2,    1.4),
 ('f05_erratic','steps',  0,21, 70,   1300, 220),

 ('f06_dropout','temp_c', 0, 5, 37.4, 37.0, 0.12),
 ('f06_dropout','hr',     0, 5, 88,   80,   3.0),
 ('f06_dropout','spo2',   0, 5, 96,   97,   0.8),
 ('f06_dropout','pain',   0, 5, 6,    4,    0.5),
 ('f06_dropout','steps',  0, 5, 60,   240,  30),

 ('f07_combination','temp_c', 0, 6, 37.2, 37.1, 0.10), ('f07_combination','temp_c', 7,21, 37.3, 37.9, 0.10),
 ('f07_combination','hr',     0, 5, 84,   74,   2.5),  ('f07_combination','hr',     6,21, 78,   96,   3.0),
 ('f07_combination','spo2',   0,21, 96,   96,   0.8),
 ('f07_combination','pain',   0, 5, 6,    3,    0.4),  ('f07_combination','pain',   6, 9, 3,    7,    0.4),
 ('f07_combination','pain',  10,21, 7,    7,    0.4),
 ('f07_combination','steps',  0, 7, 90,   500,  40),   ('f07_combination','steps',  8,21, 500,  150,  40),

 -- Tighter noise than the others on purpose. This patient's headline reading is
 -- 37.9, a tenth below the 38.0 band edge, so noise of 0.10 rounds some days up
 -- into the next band and scores 2 x weight 3 = 6, which is the review cut-off.
 -- The fixture is testing that a low fever is absorbed, not that a reading
 -- sitting on a band edge falls the right side of it.
 ('f08_early_fever','temp_c', 0, 3, 37.9, 37.8, 0.04), ('f08_early_fever','temp_c', 4,21, 37.0, 36.8, 0.10),
 ('f08_early_fever','hr',     0, 3, 96,   88,   3.0),  ('f08_early_fever','hr',     4,21, 84,   72,   3.0),
 ('f08_early_fever','spo2',   0,21, 95,   97,   0.8),
 ('f08_early_fever','pain',   0, 3, 7,    7,    0.4),  ('f08_early_fever','pain',   4,21, 5,    2,    0.5),
 ('f08_early_fever','steps',  0,21, 60,   1200, 60),

 ('f09_collect_score','temp_c', 0, 4, 37.2, 37.0, 0.08), ('f09_collect_score','temp_c', 5,21, 37.6, 37.7, 0.08),
 ('f09_collect_score','hr',     0,21, 84,   76,   3.0),
 ('f09_collect_score','spo2',   0,21, 96,   97,   0.8),
 ('f09_collect_score','pain',   0,21, 6,    3,    0.5),
 ('f09_collect_score','steps',  0,21, 80,   1000, 60),

 ('f11_one_day_spike','temp_c', 0,21, 37.2, 36.8, 0.10),
 ('f11_one_day_spike','hr',     0,21, 84,   74,   3.0),
 ('f11_one_day_spike','spo2',   0,21, 96,   98,   0.8),
 ('f11_one_day_spike','pain',   0, 8, 6,    3,    0.3),
 ('f11_one_day_spike','pain',   9, 9, 6,    6,    0.0),
 ('f11_one_day_spike','pain',  10,21, 3,    2,    0.3),
 ('f11_one_day_spike','steps',  0,21, 80,   1200, 60),

 ('f12_mobility_drop','temp_c', 0,21, 37.2, 36.8, 0.10),
 ('f12_mobility_drop','hr',     0,21, 84,   74,   3.0),
 ('f12_mobility_drop','spo2',   0,21, 96,   98,   0.8),
 ('f12_mobility_drop','pain',   0,21, 6,    3,    0.5),
 ('f12_mobility_drop','steps',  0,11, 100,  1200, 60), ('f12_mobility_drop','steps',12,21, 400, 380, 40),

 ('f13_out_of_window','temp_c', 0,21, 37.2, 36.8, 0.10),
 ('f13_out_of_window','hr',     0,21, 84,   74,   3.0),
 ('f13_out_of_window','spo2',   0,21, 96,   98,   0.8),
 ('f13_out_of_window','pain',   0,21, 6,    3,    0.5),
 ('f13_out_of_window','steps',  0,21, 80,   1100, 60);

-- ---- boolean and ordinal overrides
insert into fx_discrete (fixture, parameter_code, day_from, day_to, value_bool, value_code) values
 ('f02_slow_burn','drainage',  6,21, true, null),
 ('f02_slow_burn','chills',   11,21, true, null),
 ('f03_dvt','calf_pain',       4,21, true, null),
 ('f04_pe','breathless',       6, 8, true, null),
 -- f09: reported from day 2, well before score_from_day = 5
 ('f09_collect_score','drainage', 2,21, true, null),
 -- progress milestones
 ('f01_smooth','knee_bend',   14,16, null, 'chair'), ('f01_smooth','knee_bend',  17,21, null, 'car'),
 ('f01_smooth','walk_aid',    14,17, null, 'crutch'),('f01_smooth','walk_aid',   18,21, null, 'cane'),
 ('f05_erratic','knee_bend',  14,21, null, 'car'),   ('f05_erratic','walk_aid',  14,21, null, 'cane'),
 ('f12_mobility_drop','knee_bend',14,21, null, 'car'),
 ('f12_mobility_drop','walk_aid', 14,21, null, 'cane'),
 -- f13: nurse types a knee bend on day 5. collect_from_day is 14, so this
 -- value is outside the collect window entirely. Store it, never score it.
 ('f13_out_of_window','knee_bend', 5, 5, null, 'chair'),
 ('f13_out_of_window','knee_bend',14,21, null, 'car'),
 ('f13_out_of_window','walk_aid', 14,21, null, 'cane');

insert into fx_gap (fixture, day) values
 ('f05_erratic',2),('f05_erratic',3),('f05_erratic',6),('f05_erratic',9),('f05_erratic',10),
 ('f05_erratic',13),('f05_erratic',17),('f05_erratic',18),('f05_erratic',19),
 ('f08_early_fever',12),
 ('f11_one_day_spike',15);

insert into fx_source (fixture, day, source) values
 ('f13_out_of_window', 5, 'nurse');      -- phone call, not the app

insert into fx_expect
    (fixture, escalate_from, escalate_to, expect_tier, must_not_escalate, expect_reasons, note) values
 ('f01_smooth',        null,null,'normal',    true,  null,
  'False-positive control.'),
 ('f02_slow_burn',        8,  11,'critical',  false, array['fever_returned','pain_rising'],
  'Temperature settles days 4-6 before climbing, which is what arms the detector.'),
 ('f03_dvt',              4,   4,'critical',  false, array['calf_pain'],
  'Override fires the day the flag turns true.'),
 ('f04_pe',               6,   6,'emergency', false, array['breathless'],
  'Bypasses scoring. Patient guidance shown client-side.'),
 ('f05_erratic',       null,null,'normal',    true,  null,
  'Gaps must not be read as deterioration.'),
 ('f06_dropout',          6,   7,'missed',    false, array['missed_check_in'],
  'Raised by the absence sweep, never by ingest.'),
 ('f07_combination',      9,  12,'critical',  false, array['pain','temp_c'],
  'Weighted total only. No signal reaches band 3.'),
 ('f08_early_fever',   null,null,'normal',    true,  null,
  'Day-banded corridor must absorb 37.9 and pain 7 on days 0-3.'),
 ('f09_collect_score',    5,   6,'review',    false, array['drainage'],
  'Drainage rows exist from day 2. No drainage signal before day 5.'),
 ('f11_one_day_spike', null,null,'review',    true,  array['pain_rising'],
  'Hysteresis holds a one-day blip below critical.'),
 ('f12_mobility_drop', null,null,'review',    true,  array['mobility_regression'],
  'Personal best 1200 halves to 400 at day 12.'),
 ('f13_out_of_window', null,null,'normal',    true,  null,
  'knee_bend on day 5 is stored but must produce no signal.');


-- ---------------------------------------------------------------------
-- 4. Patients, episodes, baselines
-- ---------------------------------------------------------------------
-- Episodes go first: patient_episode.patient_id is ON DELETE RESTRICT,
-- so the patient rows cannot be removed while an episode still points at
-- them. Deleting the episode cascades to its check-ins, evaluations and
-- alerts.
delete from txn.patient_episode e
 using txn.patient p
 where p.patient_id = e.patient_id
   and p.mrn like 'FX-%';

delete from txn.patient where mrn like 'FX-%';

insert into txn.patient (patient_id, hospital_id, mrn, patient_name, phone_e164, language_code,
                         gender, address_line, address_city, address_district, address_state, address_postal_code)
select md5(f.fixture)::uuid, h.hospital_id,
       'FX-' || upper(substr(f.fixture, 2, 2)),
       f.display_name,
       '+9198' || lpad((abs(hashtext(f.fixture)) % 100000000)::text, 8, '0'),
       'en',
       x.gender, x.street, 'Coimbatore', 'Coimbatore', 'Tamil Nadu', x.postal_code
from fx_patient f
join fx_person x on x.fixture = f.fixture
cross join (select hospital_id from meta.hospital where hospital_code = 'CBE-01') h;

insert into txn.patient_contact (patient_id, priority, contact_name, relationship, phone_e164)
select md5(x.fixture)::uuid, 1, x.contact_name, x.relationship,
       '+9197' || lpad((abs(hashtext(x.fixture || ':contact')) % 100000000)::text, 8, '0')
from fx_person x;

-- enrolled_by is a foreign key to meta.admin_user. Fixtures are loaded by
-- a script, not enrolled by a clinician, so it is left null.
insert into txn.patient_episode
    (episode_id, patient_id, hospital_id, procedure_id, ruleset_id,
     surgery_date, discharge_date, monitoring_ends_on,
     consent_version, consent_at, enrolled_by, status)
select md5(f.fixture || ':ep')::uuid, md5(f.fixture)::uuid,
       h.hospital_id, sp.procedure_id, r.ruleset_id,
       c.today - 25, c.today - 21, c.today + 63,
       'v1', now() - interval '25 days', null, 'active'
from fx_patient f
cross join fx_clock c
cross join (select hospital_id from meta.hospital where hospital_code = 'CBE-01') h
cross join (select procedure_id from meta.surgical_procedure where procedure_code = 'TKR') sp
cross join (select ruleset_id from meta.ruleset where version = '1.0.0') r;

insert into txn.episode_baseline (episode_id, parameter_id, value_num, value_bool, value_code)
select md5(f.fixture || ':ep')::uuid, p.parameter_id, v.num, null, v.code
from fx_patient f
join fx_person x on x.fixture = f.fixture
cross join lateral (values
    ('temp_c',    f.base_temp,          null),
    ('hr',        f.base_hr::numeric,   null),
    ('spo2',      f.base_spo2::numeric, null),
    ('pain',      f.base_pain::numeric, null),
    ('knee_bend', null::numeric,        'chair'),
    ('walk_aid',  null::numeric,        'walker'),
    ('height_cm', round(case x.gender when 'female' then 154 else 167 end
                        + txn.fx_noise(f.fixture || ':height', 6)),     null),
    ('weight_kg', round(72 + txn.fx_noise(f.fixture || ':weight', 14), 1), null),
    ('bp_sys',    round(132 + txn.fx_noise(f.fixture || ':bp_sys', 12)),   null),
    ('bp_dia',    round(82 + txn.fx_noise(f.fixture || ':bp_dia', 7)),     null)
) as v(pcode, num, code)
join meta.parameter p on p.parameter_code = v.pcode;


-- ---------------------------------------------------------------------
-- 5. Check-ins
-- ---------------------------------------------------------------------
with submitted as (
    select f.fixture, d.day
    from fx_patient f
    cross join lateral generate_series(0, f.last_day) d(day)
    where not exists (select 1 from fx_gap g where g.fixture = f.fixture and g.day = d.day)
)
insert into txn.patient_check_in
    (check_in_id, episode_id, day_after_discharge,
     submitted_at, captured_at, source, idempotency_key, photo_key)
select md5(s.fixture || ':ci:' || s.day)::uuid,
       md5(s.fixture || ':ep')::uuid,
       s.day,
       ((c.today - 21 + s.day) + time '08:12') at time zone c.timezone,
       ((c.today - 21 + s.day) + time '08:09') at time zone c.timezone,
       coalesce(src.source, 'patient'),
       'fx-' || s.fixture || '-' || s.day,
       case when s.day <= 14 then
            'wounds/' || s.fixture || '/day' || lpad(s.day::text, 2, '0') || '.jpg' end
from submitted s
cross join fx_clock c
left join fx_source src on src.fixture = s.fixture and src.day = s.day;


-- ---------------------------------------------------------------------
-- 6. Numeric values
-- ---------------------------------------------------------------------
insert into txn.patient_check_in_value (check_in_id, parameter_id, value_num)
select ci.check_in_id, p.parameter_id,
       greatest(coalesce(p.value_min, -999999),
         least(coalesce(p.value_max, 999999),
           round(
             case when c.day_to = c.day_from then c.start_val
                  else c.start_val + (c.end_val - c.start_val)
                       * (g.day - c.day_from)::numeric / (c.day_to - c.day_from)
             end
             + txn.fx_noise(c.fixture || c.parameter_code || g.day::text, c.noise),
             p.decimal_places)))
from fx_curve c
cross join lateral generate_series(c.day_from, c.day_to) g(day)
join meta.parameter p on p.parameter_code = c.parameter_code
join txn.patient_check_in ci on ci.check_in_id = md5(c.fixture || ':ci:' || g.day)::uuid
on conflict (check_in_id, parameter_id) do nothing;


-- The discharge baseline is the reading taken on the day of discharge, so it is
-- day 0's own value, not the resting figure the patient settles back to weeks
-- later. hr is the one measure scored as a distance from it (relative_to_baseline),
-- and leaving the two out of step made every fixture patient look tachycardic
-- through their first week: the curves start around 88 and settle to base_hr.
-- That put both false-positive controls into the review queue for no reason.
update txn.episode_baseline b
   set value_num = v.value_num
  from txn.patient_check_in c
  join txn.patient_check_in_value v on v.check_in_id = c.check_in_id
  join meta.parameter p on p.parameter_id = v.parameter_id
 where c.episode_id = b.episode_id
   and b.parameter_id = p.parameter_id
   and p.parameter_code = 'hr'
   and c.day_after_discharge = 0
   and b.episode_id in (select md5(f.fixture || ':ep')::uuid from fx_patient f);


-- ---------------------------------------------------------------------
-- 7. Boolean values
--    False by default across the COLLECT window, not the score window,
--    so drainage has a row from day 0 for every patient even though it
--    is only scored from day 5.
-- ---------------------------------------------------------------------
insert into txn.patient_check_in_value (check_in_id, parameter_id, value_bool)
select ci.check_in_id, p.parameter_id, coalesce(bool_or(d.value_bool), false)
from txn.patient_check_in ci
join txn.patient_episode e on e.episode_id = ci.episode_id
join fx_patient f on md5(f.fixture || ':ep')::uuid = e.episode_id
join meta.procedure_parameter pp on pp.ruleset_id = e.ruleset_id
join meta.parameter p on p.parameter_id = pp.parameter_id and p.parameter_type = 'boolean'
left join fx_discrete d on d.fixture = f.fixture
                       and d.parameter_code = p.parameter_code
                       and ci.day_after_discharge between d.day_from and d.day_to
where ci.day_after_discharge between pp.collect_from_day and pp.collect_to_day
group by ci.check_in_id, p.parameter_id
on conflict (check_in_id, parameter_id) do nothing;


-- ---------------------------------------------------------------------
-- 8. Ordinal values
--    Taken from fx_discrete only, with the collect window NOT enforced,
--    so f13 can place a value outside the window on purpose.
-- ---------------------------------------------------------------------
insert into txn.patient_check_in_value (check_in_id, parameter_id, value_code)
select ci.check_in_id, p.parameter_id, min(d.value_code)
from fx_discrete d
cross join lateral generate_series(d.day_from, d.day_to) gs(day)
join meta.parameter p on p.parameter_code = d.parameter_code and p.parameter_type = 'ordinal'
join txn.patient_check_in ci on ci.check_in_id = md5(d.fixture || ':ci:' || gs.day)::uuid
where d.value_code is not null
group by ci.check_in_id, p.parameter_id
on conflict (check_in_id, parameter_id) do nothing;


-- ---------------------------------------------------------------------
-- 9. Expectations, readable by the Python harness
-- ---------------------------------------------------------------------
create table if not exists txn.fixture_expectation (
    fixture           text     primary key,
    episode_id        uuid     not null,
    escalate_from     smallint,
    escalate_to       smallint,
    expect_tier       text     not null,
    must_not_escalate boolean  not null default false,
    expect_reasons    text[],
    note              text
);

alter table txn.fixture_expectation add column if not exists expect_reasons text[];

delete from txn.fixture_expectation;

insert into txn.fixture_expectation
select x.fixture, md5(x.fixture || ':ep')::uuid, x.escalate_from, x.escalate_to,
       x.expect_tier, x.must_not_escalate, x.expect_reasons, x.note
from fx_expect x;

commit;
