-- Phase 9 (dynamic orchestration) — planner effort on sessions.
-- standard: planner fires only on explicit request ("ultra"/"workflow" keyword)
-- high:     same as standard for now (reserved for tuned heuristics)
-- ultra:    planner fires automatically for any substantive message

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS effort TEXT NOT NULL DEFAULT 'standard';

DO $$
BEGIN
    ALTER TABLE sessions
        ADD CONSTRAINT sessions_effort_check CHECK (effort IN ('standard','high','ultra'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
