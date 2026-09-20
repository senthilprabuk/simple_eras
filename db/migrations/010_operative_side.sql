-- =====================================================================
-- Migration: 010_operative_side.sql
-- Purpose:
--   Record which knee was replaced.
--
--   The engine scores a symptom without knowing where it is, and for
--   most measures that is right. Calf pain is the exception: swelling in
--   the operated leg is usually dependent post-surgical oedema and
--   expected, while the same answer about the other leg is a far stronger
--   indication of deep vein thrombosis. The two need different responses
--   and the answer alone cannot tell them apart, so the side belongs
--   beside the patient wherever that answer is read.
--
--   Nullable on purpose. Episodes enrolled before this column existed
--   have no recorded side, and filling one in would be inventing a
--   clinical fact about a real patient. They read as "side not recorded"
--   and the enrollment form requires it from here on, so the gap closes
--   forward rather than by guesswork.
--
--   Held on the episode rather than the patient: a second replacement is
--   a second episode, and it may well be the other knee.
--
--   Run through db/migrate.py, which wraps it in a transaction.
-- =====================================================================

alter table txn.patient_episode
    add column operative_side text,
    add constraint episode_operative_side_known
        check (operative_side is null or operative_side in ('left', 'right', 'bilateral'));

comment on column txn.patient_episode.operative_side is
    'Which knee was replaced: left, right or bilateral. Null for episodes enrolled before it was captured.';
