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
  created_by     TEXT,        -- FeedUser.user_id(身份复用 Feed 的 X-User-Id)
  created_at     TEXT,
  updated_at     TEXT,
  deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_at_threads_user ON opportunities.assistant_threads(created_by);

CREATE TABLE IF NOT EXISTS opportunities.assistant_messages (
  message_id     TEXT PRIMARY KEY,
  thread_id      TEXT NOT NULL,
  role           TEXT NOT NULL,   -- user | assistant | system
  content        TEXT,
  opportunity_id TEXT,            -- 上下文快照(发该条消息时所在商机/报价,用于重建 LLM 上下文)
  quotation_id   TEXT,
  created_at     TEXT,
  deleted_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_at_msgs_thread ON opportunities.assistant_messages(thread_id);
