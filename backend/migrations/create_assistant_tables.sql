-- 第二期:全局「方案助手」AI 聊天窗骨架 — 会话表
--
-- 独立于 FeedMessage(opportunities.opportunity_messages):助手是用户<->AI 的私域上下文,
-- 不混入团队 Feed 活动流。LLM 这期不接(占位回复),表结构前向兼容——
-- 接模型时按需加 tokens / model / trace_id 列即可,无需重构。
-- 幂等:可重复执行。

CREATE TABLE IF NOT EXISTS opportunities.assistant_threads (
  thread_id      TEXT PRIMARY KEY,
  title          TEXT,
  opportunity_id TEXT,        -- 上下文锚:会话可绑定某商机(可空=全局会话)
  quotation_id   TEXT,
  entry_point    TEXT,        -- 最近入口:portal / floating_assistant / ai_office / settings
  created_by     TEXT,        -- FeedUser.user_id(身份复用 Feed 的 X-User-Id)
  created_at     TEXT,
  updated_at     TEXT,
  deleted_at     TEXT,
  reasoning_state TEXT,        -- 方案助手需求分析会话状态(JSON,与商机 extra_fields 平行)
  thread_kind     TEXT NOT NULL DEFAULT 'assistant',  -- assistant=方案助手；office_colleague=AI Office 同事会话
  colleague_role_key TEXT     -- AI Office 会话归属的同事 role_key；方案助手为空
);
CREATE INDEX IF NOT EXISTS idx_at_threads_user ON opportunities.assistant_threads(created_by);
-- Skill 预览线程（entry_point=skill_studio_preview）与正式 office 线程共用 user+role，需允许并存。
DROP INDEX IF EXISTS uq_assistant_office_thread_active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_assistant_office_thread_active
ON opportunities.assistant_threads (created_by, colleague_role_key)
WHERE thread_kind = 'office_colleague'
  AND colleague_role_key IS NOT NULL
  AND deleted_at IS NULL
  AND entry_point IS DISTINCT FROM 'skill_studio_preview';

CREATE TABLE IF NOT EXISTS opportunities.assistant_messages (
  message_id     TEXT PRIMARY KEY,
  thread_id      TEXT NOT NULL,
  role           TEXT NOT NULL,   -- user | assistant | system
  content        TEXT,
  kind           TEXT DEFAULT 'text',  -- text | analysis_trigger | analysis_result
  data           TEXT,           -- 结构化载荷 JSON(analysis_result → {plans,...} 供历史重放)
  opportunity_id TEXT,            -- 上下文快照(发该条消息时所在商机/报价,用于重建 LLM 上下文)
  quotation_id   TEXT,
  created_at     TEXT,
  deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_at_msgs_thread ON opportunities.assistant_messages(thread_id);
