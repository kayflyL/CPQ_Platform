-- 线索池：公开渠道汇聚的线索（规格 = docs/prototypes/线索池工作台-原型.html）。
-- 状态机：new → confirmed → (converting 瞬态) → assigned；确认前可 → rejected。
-- 登记表与商机详情页线索登记表同构：config_slots 与 RequirementSlots 同构（configs[]/config_relation/
-- purchase_qty/server_model/platform_type/server_type/chassis_form/warranty_years/kp_rows），
-- 转化时原样生成需求草稿，业务侧零重填。
-- expected_delivery = 期望交期（requirement_sheet_form 同步新增字段）。
-- ai_* 字段为二期 AI 初筛预留（llm_client 结构化评分），一期不读写。
-- 幂等可重跑。回滚（如需）：DROP TABLE opportunities.opportunity_leads;

CREATE TABLE IF NOT EXISTS opportunities.opportunity_leads (
    lead_id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL DEFAULT 'catalog_general',   -- catalog_model / catalog_general
    status VARCHAR NOT NULL DEFAULT 'new',
    company VARCHAR DEFAULT '',
    contact_name VARCHAR DEFAULT '',
    contact_phone VARCHAR DEFAULT '',
    contact_email VARCHAR DEFAULT '',
    requirement_text TEXT DEFAULT '',
    config_slots TEXT,                                   -- JSON：RequirementSlots 同构（configs[]/config_relation/purchase_qty/…）
    expected_delivery VARCHAR DEFAULT '',
    attachments TEXT,                                    -- JSON：[{storage_key, name, size}]
    ai_grade VARCHAR,                                    -- 二期：high/mid/low；NULL=未初筛
    ai_scores TEXT,                                      -- JSON
    ai_summary TEXT,
    ai_flags TEXT,                                       -- JSON
    ai_screened_at VARCHAR,
    dedup_count INTEGER DEFAULT 1,                       -- 同手机号未结线索重复提交并入计数
    reject_reason VARCHAR DEFAULT '',
    reject_note VARCHAR DEFAULT '',
    converted_opportunity_id VARCHAR,
    assigned_business_user_id VARCHAR,
    client_ip VARCHAR DEFAULT '',                        -- 反滥用审计留痕，UI 不展示
    user_agent VARCHAR DEFAULT '',
    created_at VARCHAR,
    updated_at VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_opportunity_leads_status ON opportunities.opportunity_leads (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_leads_phone ON opportunities.opportunity_leads (contact_phone);
