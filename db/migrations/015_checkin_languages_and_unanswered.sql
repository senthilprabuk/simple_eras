-- =====================================================================
-- Migration: 015_checkin_languages_and_unanswered.sql
-- Purpose:
--   Two gaps a demo exposed in the patient check-in.
--
--   A check-in may leave questions blank, and a blank is unknown, never
--   "no". Each evaluation now records which of the day's questions were
--   left blank, and the alert queue lists them by name for the nurse.
--
--   Patients are enrolled in English, Tamil or Hindi, but the check-in
--   spoke only English. Parameter names, questions and answer options
--   gain Tamil and Hindi alongside the English. They are draft
--   translations for demonstration: PRD NFR-6 requires professional
--   translation before patients rely on them.
-- =====================================================================

-- Tamil and Hindi wording is UTF-8; psql on Windows otherwise reads it as WIN1252.
set client_encoding = 'UTF8';

alter table txn.check_in_evaluation
    add column if not exists unanswered text[] not null default '{}';

alter table meta.parameter
    add column if not exists parameter_name_i18n jsonb not null default '{}'::jsonb;
alter table meta.procedure_parameter
    add column if not exists question_text_i18n jsonb not null default '{}'::jsonb;
alter table meta.parameter_option
    add column if not exists option_label_i18n jsonb not null default '{}'::jsonb;

create or replace view txn.v_alert_queue
with (security_invoker = true) as
select
    a.alert_id,
    a.tier,
    a.status,
    a.raised_at,
    (extract(epoch from (now() - a.raised_at)))::integer as age_secs,
    (a.acknowledged_at is not null)                      as acknowledged,
    a.acknowledged_at,
    a.acknowledged_by,
    au.full_name                                         as acknowledged_by_name,
    pt.patient_id,
    pt.patient_name,
    pt.mrn,
    e.episode_id,
    e.hospital_id,
    h.hospital_name,
    sp.procedure_code,
    ev.day_after_discharge,
    ev.reasons,
    h.ack_window_secs,
    -- the day's questions left blank, by name: blank is unknown, never "no"
    array(select prm.parameter_name
          from unnest(ev.unanswered) with ordinality as u(code, n)
          join meta.parameter prm on prm.parameter_code = u.code
          order by u.n)                                  as unanswered
from txn.alert a
join txn.check_in_evaluation ev  on ev.evaluation_id = a.evaluation_id
join txn.patient_episode e       on e.episode_id     = a.episode_id
join txn.patient pt              on pt.patient_id    = e.patient_id
join meta.hospital h             on h.hospital_id    = e.hospital_id
join meta.surgical_procedure sp  on sp.procedure_id  = e.procedure_id
left join meta.admin_user au     on au.admin_user_id = a.acknowledged_by
where a.status in ('open', 'acknowledged')
order by
    case a.tier
        when 'emergency' then 1
        when 'critical'  then 2
        when 'review'    then 3
        when 'missed'    then 4
        else 5
    end,
    a.raised_at asc;

-- Tamil and Hindi for the patient check-in: parameter names, questions and answer
-- options. DRAFT translations for demonstration; PRD NFR-6 requires professional
-- translation before patients rely on them. A question is translated only while
-- its English wording is the one below, so a reworded question falls back to
-- English rather than showing a translation of something else.
update meta.parameter p
   set parameter_name_i18n = v.names::jsonb
  from (values
    ('temp_c',      '{"ta": "உடல் வெப்பநிலை", "hi": "शरीर का तापमान"}'),
    ('hr',          '{"ta": "நாடித் துடிப்பு", "hi": "नब्ज़ (पल्स)"}'),
    ('spo2',        '{"ta": "ஆக்சிஜன் அளவு", "hi": "ऑक्सीजन स्तर"}'),
    ('pain',        '{"ta": "வலி அளவு", "hi": "दर्द का स्तर"}'),
    ('steps',       '{"ta": "நடந்த அடிகள்", "hi": "चले गए कदम"}'),
    ('calf_pain',   '{"ta": "கெண்டைக்கால் வலி அல்லது வீக்கம்", "hi": "पिंडली में दर्द या सूजन"}'),
    ('breathless',  '{"ta": "மூச்சுத் திணறல் அல்லது நெஞ்சு வலி", "hi": "साँस फूलना या सीने में दर्द"}'),
    ('drainage',    '{"ta": "காயத்திலிருந்து திரவக் கசிவு", "hi": "घाव से रिसाव"}'),
    ('chills',      '{"ta": "நடுக்கம் அல்லது குளிர்", "hi": "कँपकँपी या ठंड लगना"}'),
    ('weight_bear', '{"ta": "காலில் எடை தாங்குவதில் சிரமம்", "hi": "पैर पर वज़न डालने में कठिनाई"}'),
    ('knee_bend',   '{"ta": "முழங்கால் மடக்கும் அளவு", "hi": "घुटना मोड़ने की सीमा"}'),
    ('walk_aid',    '{"ta": "நடக்க உதவும் சாதனம்", "hi": "चलने का सहारा"}')
  ) as v(code, names)
 where p.parameter_code = v.code;

update meta.procedure_parameter pp
   set question_text_i18n = v.questions::jsonb
  from meta.parameter p,
       (values
    ('temp_c', 'What is your temperature?',
     '{"ta": "உங்கள் உடல் வெப்பநிலை என்ன?", "hi": "आपका शरीर का तापमान कितना है?"}'),
    ('pain', 'How bad is your pain right now?',
     '{"ta": "இப்போது உங்கள் வலி எவ்வளவு கடுமையாக உள்ளது?", "hi": "अभी आपका दर्द कितना तेज़ है?"}'),
    ('hr', 'What is your pulse?',
     '{"ta": "உங்கள் நாடித் துடிப்பு என்ன?", "hi": "आपकी नब्ज़ (पल्स) कितनी है?"}'),
    ('spo2', 'What is your oxygen reading?',
     '{"ta": "உங்கள் ஆக்சிஜன் அளவு என்ன?", "hi": "आपका ऑक्सीजन स्तर कितना है?"}'),
    ('steps', 'How many steps today?',
     '{"ta": "இன்று எத்தனை அடிகள் நடந்தீர்கள்?", "hi": "आज आप कितने कदम चले?"}'),
    ('breathless', 'Are you newly short of breath, or having new chest pain?',
     '{"ta": "உங்களுக்குப் புதிதாக மூச்சுத் திணறல் அல்லது நெஞ்சு வலி உள்ளதா?", "hi": "क्या आपको नई साँस फूलने की तकलीफ़ या सीने में नया दर्द है?"}'),
    ('calf_pain', 'Is the calf of your operated leg newly painful, or more swollen than your other leg?',
     '{"ta": "அறுவை சிகிச்சை செய்த காலின் கெண்டைக்காலில் புதிதாக வலி உள்ளதா, அல்லது மற்ற காலை விட அதிகமாக வீங்கியுள்ளதா?", "hi": "क्या ऑपरेशन वाले पैर की पिंडली में नया दर्द है, या वह दूसरे पैर से ज़्यादा सूजी हुई है?"}'),
    ('drainage', 'Is fluid still leaking from your wound?',
     '{"ta": "உங்கள் காயத்திலிருந்து இன்னும் திரவம் கசிகிறதா?", "hi": "क्या आपके घाव से अभी भी तरल रिस रहा है?"}'),
    ('chills', 'Have you had shivering or shaking chills?',
     '{"ta": "உங்களுக்கு நடுக்கம் அல்லது குளிர் நடுக்கம் ஏற்பட்டதா?", "hi": "क्या आपको कँपकँपी या ठंड से काँपना हुआ है?"}'),
    ('weight_bear', 'Has it suddenly become harder to put weight on your operated leg?',
     '{"ta": "அறுவை சிகிச்சை செய்த காலில் எடை தாங்குவது திடீரென்று கடினமாகிவிட்டதா?", "hi": "क्या ऑपरेशन वाले पैर पर वज़न डालना अचानक मुश्किल हो गया है?"}'),
    ('knee_bend', 'What is the furthest you can bend it?',
     '{"ta": "உங்கள் முழங்காலை எவ்வளவு தூரம் மடக்க முடிகிறது?", "hi": "आप अपना घुटना कितना मोड़ पाते हैं?"}'),
    ('walk_aid', 'What are you walking with?',
     '{"ta": "நீங்கள் எதன் உதவியுடன் நடக்கிறீர்கள்?", "hi": "आप किस सहारे से चलते हैं?"}')
       ) as v(code, english, questions)
 where pp.parameter_id = p.parameter_id
   and p.parameter_code = v.code
   and pp.question_text = v.english;

update meta.parameter_option o
   set option_label_i18n = v.labels::jsonb
  from meta.parameter p,
       (values
    ('knee_bend', 'chair',  '{"ta": "சாப்பாட்டு நாற்காலியில் உட்கார முடிகிறது", "hi": "खाने की कुर्सी पर बैठ पाते हैं"}'),
    ('knee_bend', 'car',    '{"ta": "காரில் ஏற முடிகிறது", "hi": "कार में बैठ पाते हैं"}'),
    ('knee_bend', 'bike',   '{"ta": "உடற்பயிற்சி சைக்கிளை மிதிக்க முடிகிறது", "hi": "स्थिर साइकिल चला पाते हैं"}'),
    ('walk_aid',  'walker', '{"ta": "வாக்கர் (நடை சட்டகம்)", "hi": "वॉकर"}'),
    ('walk_aid',  'crutch', '{"ta": "ஊன்றுகோல்", "hi": "बैसाखी"}'),
    ('walk_aid',  'cane',   '{"ta": "கைத்தடி", "hi": "छड़ी"}'),
    ('walk_aid',  'none',   '{"ta": "எந்த உதவியும் இல்லை", "hi": "कोई सहारा नहीं"}')
       ) as v(pcode, ocode, labels)
 where o.parameter_id = p.parameter_id
   and p.parameter_code = v.pcode
   and o.option_code = v.ocode;
