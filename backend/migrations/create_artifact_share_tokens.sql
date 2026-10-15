-- 产出物分享链接（网盘式）：artifact_share_tokens。
-- 分享 = 渲染落盘 xlsx + 免登录下载令牌（可过期/可撤销/可选提取码，下载计数留痕）。
-- 回滚（如需）：DROP TABLE opportunities.artifact_share_tokens;

CREATE TABLE IF NOT EXISTS opportunities.artifact_share_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR UNIQUE NOT NULL,
    opportunity_id VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    title VARCHAR DEFAULT '',
    view VARCHAR DEFAULT 'internal',
    template_id INTEGER,
    filename VARCHAR DEFAULT '',
    storage_key TEXT DEFAULT '',
    attachment_id VARCHAR,
    extract_code VARCHAR,
    expires_at VARCHAR,
    revoked_at VARCHAR,
    download_count INTEGER DEFAULT 0,
    last_download_at VARCHAR,
    created_by VARCHAR DEFAULT '',
    created_at VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_artifact_share_opp ON opportunities.artifact_share_tokens (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_artifact_share_token ON opportunities.artifact_share_tokens (token);
