-- =====================================================================
--  Fixture verification — read-only
--
--  Run after db/seed/02_fixtures.sql to check the load. Every query here
--  is a SELECT; nothing is written.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. The two windows side by side. Only drainage and spo2 should differ.
-- ---------------------------------------------------------------------
select p.parameter_code,
       pp.display_section,
       pp.collect_from_day || '-' || pp.collect_to_day as collect_window,
       pp.score_from_day   || '-' || pp.score_to_day   as score_window,
       case when pp.collect_from_day <> pp.score_from_day
              or pp.collect_to_day   <> pp.score_to_day
            then 'DIFFERS' end as note
from meta.procedure_parameter pp
join meta.parameter p using (parameter_id)
join meta.ruleset r using (ruleset_id)
where r.version = '1.0.0'
order by pp.display_order;


-- ---------------------------------------------------------------------
-- 2. f09 — the whole point of the split.
--    Expect: rows present from day 0 (collected), is_scored false on
--    days 0-4, true from day 5. If the engine produces a drainage signal
--    on day 2, the score window is not wired up.
-- ---------------------------------------------------------------------
select ci.day_after_discharge                          as day,
       v.value_bool                                    as drainage_reported,
       ci.day_after_discharge >= pp.collect_from_day   as is_collected,
       ci.day_after_discharge >= pp.score_from_day     as is_scored
from txn.patient_check_in ci
join txn.patient_check_in_value v using (check_in_id)
join meta.parameter p
     on p.parameter_id = v.parameter_id and p.parameter_code = 'drainage'
join txn.patient_episode e on e.episode_id = ci.episode_id
join meta.procedure_parameter pp
     on pp.ruleset_id = e.ruleset_id and pp.parameter_id = p.parameter_id
where ci.episode_id = md5('f09_collect_score:ep')::uuid
  and ci.day_after_discharge <= 8
order by day;


-- ---------------------------------------------------------------------
-- 3. f13 — a value that arrived outside the collect window entirely.
--    Expect one row on day 5 with in_collect_window = false and
--    source = 'nurse'. It must be stored and must not be scored.
-- ---------------------------------------------------------------------
select ci.day_after_discharge as day,
       ci.source,
       v.value_code,
       ci.day_after_discharge between pp.collect_from_day and pp.collect_to_day
           as in_collect_window
from txn.patient_check_in ci
join txn.patient_check_in_value v using (check_in_id)
join meta.parameter p
     on p.parameter_id = v.parameter_id and p.parameter_code = 'knee_bend'
join txn.patient_episode e on e.episode_id = ci.episode_id
join meta.procedure_parameter pp
     on pp.ruleset_id = e.ruleset_id and pp.parameter_id = p.parameter_id
where ci.episode_id = md5('f13_out_of_window:ep')::uuid
order by day;


-- ---------------------------------------------------------------------
-- 4. Load summary. Expect 14 rows, 281 check-ins in total.
--    f15 is the one row where values_recorded is far below the others:
--    two answers a day rather than ten.
-- ---------------------------------------------------------------------
select x.fixture,
       count(distinct ci.check_in_id)                           as check_ins,
       count(v.parameter_id)                                    as values_recorded,
       max(ci.day_after_discharge)                              as last_day,
       x.expect_tier,
       coalesce(array_to_string(x.expect_reasons, ', '), '-')   as expect_reasons
from txn.fixture_expectation x
join txn.patient_check_in ci on ci.episode_id = x.episode_id
left join txn.patient_check_in_value v on v.check_in_id = ci.check_in_id
group by x.fixture, x.expect_tier, x.expect_reasons
order by x.fixture;


-- ---------------------------------------------------------------------
-- 5. Window construction for the erratic reporter.
--    Days 2, 3, 6, 9 and 10 must come back as NULL rows, not absent rows.
-- ---------------------------------------------------------------------
with tracked as (
    select pp.parameter_id, p.parameter_code, pp.collect_from_day, pp.collect_to_day
    from txn.patient_episode e
    join meta.procedure_parameter pp on pp.ruleset_id = e.ruleset_id
    join meta.parameter p using (parameter_id)
    where e.episode_id = md5('f05_erratic:ep')::uuid
      and p.parameter_code in ('temp_c', 'pain')
),
latest as (
    select distinct on (ci.day_after_discharge, v.parameter_id)
           ci.day_after_discharge, v.parameter_id, v.value_num
    from txn.patient_check_in ci
    join txn.patient_check_in_value v using (check_in_id)
    where ci.episode_id = md5('f05_erratic:ep')::uuid
    order by ci.day_after_discharge, v.parameter_id, ci.submitted_at desc
)
select d.day, t.parameter_code, l.value_num
from generate_series(0, 21) d(day)
cross join tracked t
left join latest l
       on l.day_after_discharge = d.day and l.parameter_id = t.parameter_id
where d.day between t.collect_from_day and t.collect_to_day
order by t.parameter_code, d.day;
