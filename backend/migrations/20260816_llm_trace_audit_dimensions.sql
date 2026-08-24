-- Phase 2/3: audit LLM/tool traces by user, AI role, and tool.
BEGIN;

ALTER TABLE rules.llm_trace
ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) DEFAULT '';

ALTER TABLE rules.llm_trace
ADD COLUMN IF NOT EXISTS role_key VARCHAR(80) DEFAULT '';

ALTER TABLE rules.llm_trace
ADD COLUMN IF NOT EXISTS tool_name VARCHAR(80) DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_llm_trace_user ON rules.llm_trace(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_trace_role ON rules.llm_trace(role_key);
CREATE INDEX IF NOT EXISTS idx_llm_trace_tool ON rules.llm_trace(tool_name);

COMMIT;
