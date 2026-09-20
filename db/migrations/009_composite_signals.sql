-- =====================================================================
-- Migration: 009_composite_signals.sql
-- Purpose:
--   Give a ruleset somewhere to declare the signals that read every
--   measure at once instead of belonging to any single one.
--
--   Every other rule hangs off a measure in meta.procedure_parameter,
--   but the specification's `streak` detector asks whether ANYTHING has
--   been abnormal for several days running. It has no parameter to hang
--   off, so it belongs to the ruleset: a patient who is never quite bad
--   enough on any one day still surfaces.
--
--   Shape: {"trends": [{"name": ..., "detector": ..., "weight": ..., ...}]}
--   validated by backend/app/services/scoring_config.py.
--
--   The immutability guard is widened at the same time. A published
--   ruleset may still only be retired, and these rules are part of what
--   must not change underneath the patients enrolled on it.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

alter table meta.ruleset
    add column composite_config jsonb not null default '{}'::jsonb,
    add constraint ruleset_composite_is_object
        check (jsonb_typeof(composite_config) = 'object');

create or replace function meta.ruleset_guard() returns trigger
language plpgsql as $$
begin
    if old.status = 'draft' then
        return new;
    end if;
    -- a published version may be retired, and nothing else about it may change
    if old.status = 'approved' and new.status = 'retired'
       and (new.procedure_id, new.version, new.review_at, new.critical_at, new.max_points_per_parameter,
            new.approved_by, new.approved_at, new.notes, new.composite_config)
           is not distinct from
           (old.procedure_id, old.version, old.review_at, old.critical_at, old.max_points_per_parameter,
            old.approved_by, old.approved_at, old.notes, old.composite_config)
    then
        return new;
    end if;
    raise exception 'ruleset % is %; only a draft can be changed', old.version, old.status
        using errcode = 'check_violation';
end $$;
