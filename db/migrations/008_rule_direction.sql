-- =====================================================================
-- Migration: 008_rule_direction.sql
-- Purpose:
--   Record which way each numeric measure goes wrong, as
--   scoring_config.direction = 'higher_is_worse' | 'higher_is_better'.
--
--   A fever rises, oxygen falls. Until now the engine read that off the
--   bands: whichever end scores nothing was taken to be the safe end.
--   That inference says nothing about a reading no band covers, and is
--   silently wrong for a rule whose bands all score, so the rule now
--   states it and the API refuses a numeric rule without it.
--
--   1. Backfill every numeric binding from the bands it already has,
--      giving exactly what the old inference gave.
--   2. Constrain the vocabulary, so no writer can store a typo.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

-- 1. Backfill ------------------------------------------------------------
--    A detector watches for a fall from the patient's own best, so higher is
--    better. Otherwise the first band decides: scoring nothing at the low end
--    means the high end is the worrying one. Every bands_by_day span in this
--    data agrees with its siblings, so reading the lowest-keyed one is enough.
update meta.procedure_parameter pp
   set scoring_config = pp.scoring_config || jsonb_build_object(
           'direction',
           case
             when pp.scoring_config ? 'detector' then 'higher_is_better'
             when coalesce(
                      pp.scoring_config -> 'bands' -> 0 ->> 2,
                      (select s.value -> 0 ->> 2
                         from jsonb_each(pp.scoring_config -> 'bands_by_day') s
                        order by s.key
                        limit 1)
                  )::numeric = 0 then 'higher_is_worse'
             else 'higher_is_better'
           end)
 where exists (select 1
                 from meta.parameter p
                where p.parameter_id = pp.parameter_id
                  and p.parameter_type = 'numeric')
   and not (pp.scoring_config ? 'direction');

-- 2. Vocabulary ----------------------------------------------------------
alter table meta.procedure_parameter
    add constraint ppm_direction_known check (
        not (scoring_config ? 'direction')
        or scoring_config ->> 'direction' in ('higher_is_worse', 'higher_is_better')
    );
