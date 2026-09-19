-- =====================================================================
-- Migration: 002_remove_redness_parameter.sql
-- Purpose:
--   Retire the 'redness' (Redness spreading) parameter from the registry
--   and from every ruleset that binds it, along with all recorded answers.
--
--   db/seed/01_reference.sql no longer defines it, but that file only adds
--   missing rows, so a database seeded before this change keeps the
--   parameter until this migration runs.
--
--   This edits approved ruleset 1.0.0 in place rather than issuing a new
--   version, which is acceptable only while no real patient data exists.
--
--   Afterwards, re-run db/seed/02_fixtures.sql to rebuild the fixture
--   expectations, which referenced this parameter.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

-- Dependents first: check-in values and bindings reference the parameter
-- with ON DELETE RESTRICT, and baselines with NO ACTION.
delete from txn.patient_check_in_value v
 using meta.parameter p
 where p.parameter_id = v.parameter_id
   and p.parameter_code = 'redness';

delete from txn.episode_baseline b
 using meta.parameter p
 where p.parameter_id = b.parameter_id
   and p.parameter_code = 'redness';

delete from meta.procedure_parameter pp
 using meta.parameter p
 where p.parameter_id = pp.parameter_id
   and p.parameter_code = 'redness';

delete from meta.parameter where parameter_code = 'redness';
