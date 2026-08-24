-- Phase 2/3: record the latest chat entry source for AI employee threads.
-- Values are frontend-provided: portal / floating_assistant / ai_office / settings.
BEGIN;

ALTER TABLE opportunities.assistant_threads
ADD COLUMN IF NOT EXISTS entry_point TEXT;

COMMIT;
