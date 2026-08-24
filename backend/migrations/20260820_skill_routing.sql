BEGIN;

ALTER TABLE rules.skill_catalog
ADD COLUMN IF NOT EXISTS hit_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE rules.skill_catalog
DROP COLUMN IF EXISTS trigger_rules;

UPDATE rules.skill_catalog SET hit_count = 0 WHERE hit_count IS NULL;

COMMIT;
