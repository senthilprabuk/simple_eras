-- =====================================================================
--  Reference data — the minimum a working installation needs
--
--  One hospital, one procedure, the parameter registry, and the approved
--  TKR ruleset with all twelve parameters bound to it.
--
--  Requires: db/schema/*.sql
--  Idempotent: safe to re-run. Parameter bindings are upserted so window
--  and wording changes take effect; everything else is left alone.
-- =====================================================================

begin;

-- ---------------------------------------------------------------------
-- Hospital and procedure
--   backend/seed/seed_demo.py renames hospital 1 for the demo dataset.
-- ---------------------------------------------------------------------
insert into meta.hospital (hospital_code, hospital_name, city)
values ('CBE-01', 'Example Ortho Hospital', 'Coimbatore')
on conflict (hospital_code) do nothing;

insert into meta.surgical_procedure
    (procedure_code, procedure_name, procedure_desc, observation_days)
values
    ('TKR', 'Total knee replacement',
     'Primary unilateral total knee arthroplasty, post-discharge monitoring', 84)
on conflict (procedure_code) do nothing;

insert into meta.hospital_procedure (hospital_id, procedure_id)
select h.hospital_id, p.procedure_id
from meta.hospital h, meta.surgical_procedure p
where h.hospital_code = 'CBE-01' and p.procedure_code = 'TKR'
on conflict (hospital_id, procedure_id) do nothing;


-- ---------------------------------------------------------------------
-- Parameter registry
--   The last four are recorded once at enrollment and never asked in a
--   check-in, so no ruleset binds them. loinc_code is the FHIR
--   Observation.code; the yes/no symptoms have no standard code.
-- ---------------------------------------------------------------------
insert into meta.parameter
    (parameter_code, parameter_name, parameter_type, unit,
     value_min, value_max, decimal_places, concerning_when_true, loinc_code)
values
    ('temp_c',      'Temperature',                  'numeric', 'C',    30,    45, 1, null, '8310-5'),
    ('hr',          'Pulse',                        'numeric', 'bpm',  30,   220, 0, null, '8867-4'),
    ('spo2',        'Oxygen saturation',            'numeric', '%',    50,   100, 0, null, '59408-5'),
    ('pain',        'Pain score',                   'numeric', null,    0,    10, 0, null, '72514-3'),
    ('steps',       'Steps walked',                 'numeric', null,    0, 50000, 0, null, '55423-8'),
    ('calf_pain',   'Calf pain or swelling',        'boolean', null, null,  null, 0, true, null),
    ('breathless',  'Breathlessness or chest pain', 'boolean', null, null,  null, 0, true, null),
    ('drainage',    'Wound still leaking',          'boolean', null, null,  null, 0, true, null),
    ('chills',      'Shivering or chills',          'boolean', null, null,  null, 0, true, null),
    ('weight_bear', 'Harder to bear weight',        'boolean', null, null,  null, 0, true, null),
    ('knee_bend',   'Knee bend reached',            'ordinal', null, null,  null, 0, null, null),
    ('walk_aid',    'Walking aid in use',           'ordinal', null, null,  null, 0, null, null),
    ('height_cm',   'Height',                       'numeric', 'cm',  100,   230, 0, null, '8302-2'),
    ('weight_kg',   'Weight',                       'numeric', 'kg',   25,   250, 1, null, '29463-7'),
    ('bp_sys',      'Blood pressure, systolic',     'numeric', 'mmHg', 60,   260, 0, null, '8480-6'),
    ('bp_dia',      'Blood pressure, diastolic',    'numeric', 'mmHg', 30,   160, 0, null, '8462-4')
on conflict (parameter_code) do nothing;

insert into meta.parameter_option (parameter_id, option_code, option_label, ordinal_rank)
select p.parameter_id, v.code, v.label, v.rank
from meta.parameter p
join (values
        ('knee_bend','chair', 'Sit in a dining chair',    1),
        ('knee_bend','car',   'Get into a car',           2),
        ('knee_bend','bike',  'Pedal a stationary bike',  3),
        ('walk_aid', 'walker','Walking frame',            1),
        ('walk_aid', 'crutch','Crutches',                 2),
        ('walk_aid', 'cane',  'Walking stick',            3),
        ('walk_aid', 'none',  'No aid',                   4)
     ) as v(pcode, code, label, rank) on v.pcode = p.parameter_code
on conflict (parameter_id, option_code) do nothing;


-- ---------------------------------------------------------------------
-- Approved TKR ruleset
-- ---------------------------------------------------------------------
--   composite_config would hold the signals that read every measure at once,
--   such as {"trends":[{"name":"persistent_abnormal","detector":"streak",
--   "weight":1,"score":1,"min_days":3}]}. It is deliberately empty here.
--
--   The engine supports the streak detector and it is covered by tests, but
--   adding it to this ruleset at weight 1 takes both false-positive control
--   patients (f01_smooth, f13_out_of_window) from 4 points to 5 and so into
--   the review queue: three days of mild pain is enough to arm it, which
--   describes most of a normal recovery. Turning it on is a calibration
--   decision for a surgeon, recorded as a new approved version — not a
--   default. tests/test_fixture_expectations.py is what caught that.
insert into meta.ruleset
    (procedure_id, version, review_at, critical_at, status, approved_by, approved_at)
select procedure_id, '1.0.0', 5, 12, 'approved', 'Dr Example', now()
from meta.surgical_procedure where procedure_code = 'TKR'
on conflict (procedure_id, version) do nothing;


-- ---------------------------------------------------------------------
-- Parameter bindings — all twelve, with both windows
--
--   Two rows where the windows deliberately differ:
--     drainage : ask from day 0, alert from day 5. Duration of drainage
--                is the predictor, so hiding the question until day 5
--                would throw away the very thing that matters.
--     spo2     : ask to day 42, alert to day 14. One extra tap buys a
--                longer trend after clot risk stops warranting an alert.
-- ---------------------------------------------------------------------
insert into meta.procedure_parameter
    (ruleset_id, parameter_id, display_order, display_section,
     collect_from_day, collect_to_day, score_from_day, score_to_day,
     parameter_weight, scoring_config, question_text)
select r.ruleset_id, p.parameter_id, v.ord, v.section,
       v.c_from, v.c_to, v.s_from, v.s_to,
       v.weight, v.cfg::jsonb, v.question
from meta.ruleset r
join meta.surgical_procedure sp
     on sp.procedure_id = r.procedure_id and sp.procedure_code = 'TKR'
join (values
    --  code          ord section     c_from c_to s_from s_to  wt
    ('temp_c',        1,'readings',  0, 42,  0, 42, 3,
     '{"direction":"higher_is_worse","bands":[[0,37.5,0],[37.5,38.0,1],[38.0,38.5,2],[38.5,99,3]],'
     -- A temperature that settles for two days and climbs again on day six is a
     -- far stronger infection signal than the same reading on day one, and no
     -- absolute threshold separates them. slow_burn catches the creep that
     -- never reaches 37.5 on any single day.
     || '"trends":[{"name":"fever_returned","detector":"reemergence",'
     || '"weight":3,"score":3,"normal_days_required":2},'
     || '{"name":"slow_burn","detector":"monotonic_rise","weight":2,"score":2,'
     || '"window_days":5,"min_observations":3,"min_total_rise":0.8}]}',
     'What is your temperature?'),
    ('pain',          2,'readings',  0, 84,  0, 84, 2,
     '{"direction":"higher_is_worse","bands_by_day":{"0-3":[[0,8,0],[8,10,1],[10,99,3]],'
     || '"4-10":[[0,4,0],[4,6,1],[6,8,2],[8,99,3]],'
     || '"11-84":[[0,3,0],[3,5,1],[5,7,2],[7,99,3]]},'
     -- Scored on the gap from this patient's own recent average, so someone
     -- sitting at 6 every day raises nothing while a jump from 3 to 6 does.
     || '"trends":[{"name":"pain_rising","detector":"delta_vs_rolling_mean",'
     || '"weight":2,"window_days":3,"min_observations":3,'
     || '"bands":[[0,2,0],[2,3,1],[3,4,2],[4,99,3]]}]}',
     'How bad is your pain right now?'),
    ('hr',            3,'readings',  0, 42,  0, 42, 2,
     '{"direction":"higher_is_worse","relative_to_baseline":true,"bands":[[0,10,0],[10,20,1],[20,30,2],[30,999,3]]}',
     'What is your pulse?'),
    ('spo2',          4,'readings',  0, 42,  0, 14, 2,
     '{"direction":"higher_is_better","bands":[[0,90,3],[90,93,2],[93,95,1],[95,101,0]]}',
     'What is your oxygen reading?'),
    ('steps',         5,'readings',  0, 84,  0, 84, 1,
     -- Measured against this patient's own best rather than a population figure,
     -- so it reads the same at 300 steps a day and at 3000.
     '{"direction":"higher_is_better","trends":[{"name":"mobility_regression",'
     || '"detector":"drop_from_personal_best","weight":1,"score":2,"drop_fraction":0.5}]}',
     'How many steps today?'),
    ('breathless',    6,'checks',    0, 42,  0, 42, 3,
     '{"binary_score":3,"emergency":true}',
     'Are you newly short of breath, or having new chest pain?'),
    ('calf_pain',     7,'checks',    0, 42,  0, 42, 3,
     '{"binary_score":3}',
     'Is the calf of your operated leg newly painful, or more swollen than your other leg?'),
    ('drainage',      8,'checks',    0, 28,  5, 28, 2,
     '{"binary_score":2}',
     'Is fluid still leaking from your wound?'),
    ('chills',       10,'checks',    0, 28,  0, 28, 3,
     '{"binary_score":3}',
     'Have you had shivering or shaking chills?'),
    ('weight_bear',  11,'checks',    0, 42,  0, 42, 3,
     '{"binary_score":3}',
     'Has it suddenly become harder to put weight on your operated leg?'),
    ('knee_bend',    12,'progress', 14, 84, 14, 84, 1,
     '{"milestone":{"14":"chair","42":"car","84":"bike"},"score":2}',
     'What is the furthest you can bend it?'),
    ('walk_aid',     13,'progress', 14, 84, 14, 84, 1,
     '{"milestone":{"14":"crutch","42":"cane","84":"none"},"score":1}',
     'What are you walking with?')
) as v(pcode, ord, section, c_from, c_to, s_from, s_to, weight, cfg, question) on true
join meta.parameter p on p.parameter_code = v.pcode
where r.version = '1.0.0'
on conflict (ruleset_id, parameter_id) do update set
    display_order    = excluded.display_order,
    display_section  = excluded.display_section,
    collect_from_day = excluded.collect_from_day,
    collect_to_day   = excluded.collect_to_day,
    score_from_day   = excluded.score_from_day,
    score_to_day     = excluded.score_to_day,
    parameter_weight = excluded.parameter_weight,
    scoring_config   = excluded.scoring_config,
    question_text    = excluded.question_text;


-- ---------------------------------------------------------------------
-- WhatsApp templates — English defaults only. Tamil and Hindi are left for
-- the hospital to write rather than machine-translating clinical guidance.
-- ---------------------------------------------------------------------
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
     '{patient_first_name}, you reported a symptom that needs attention today. Please call {hospital_name} now. If you have chest pain or severe breathlessness, call emergency services immediately.'),
    ('checkin_confirmation',
     'Thank you {patient_first_name}. Your day {post_op_day} check-in has reached {hospital_name}.')
) as t(template_key, body)
where h.hospital_code = 'CBE-01'
on conflict do nothing;

-- Default WhatsApp Business account for St. Mary's Orthopedic Center
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

commit;
