-- Migration v4: Soft-delete for meetings
--
-- Goal: when user deletes a meeting, hide it from list / search /
-- dashboard / wordcloud, BUT keep counting its duration in monthly /
-- daily usage so users can't game the quota by deleting old meetings.
--
-- Strategy: add a `deleted_at TIMESTAMPTZ` column. Delete = UPDATE
-- deleted_at = NOW() (set in application code).
--
-- Rollout is safe: existing rows default to NULL → treated as active.

ALTER TABLE meetings
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

-- Partial index so all "WHERE deleted_at IS NULL" lookups stay fast
-- without bloating the index with tombstones.
CREATE INDEX IF NOT EXISTS idx_meetings_user_active
  ON meetings (user_id, created_at DESC)
  WHERE deleted_at IS NULL;
