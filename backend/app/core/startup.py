"""
Startup event to initialize rules database tables and default rules.
"""
from app.models.base import rules_engine, l6_history_engine, opp_engine, Base
from app.models.rules import KPCategoryMapping, MatchingRule
from app.models.l6 import L6PriceHistory
from app.models.spec_template import SpecTemplate
# Feed (collaboration) models — register with Base.metadata before create_all
from app.models.feed_user import FeedUser
from app.models.feed_message import FeedMessage
from app.models.feed_attachment import FeedAttachment
from app.models.reasoning_flow import ReasoningFlow, ReasoningNodeConfig  # 推理流可视化配置（注册 metadata 供 create_all 建表）
from app.models.skill_config import SkillPromptTemplate, ReasoningNodeDefault  # 技能提示词/推理节点默认契约（DB 唯一权威，注册 metadata 供 create_all 建表）
from app.models.skill import SkillCatalog  # Skill 元数据独立表（注册 metadata 供 create_all 建表）
from app.models.llm_trace import LLMTrace  # LLM 调用审计 trace（P3 指标）（注册 metadata 供 create_all 建表）
from app.models.compatibility_rule import CompatibilityRule  # 兼容性规则引擎（注册 metadata 供 create_all 建表）
from app.models.office_event import OfficeEvent  # AI 办公室事件审计（注册 metadata 供 create_all 建表）
from app.models.office_governance import OfficeGovernanceItem  # AI 办公室治理审批（注册 metadata 供 create_all 建表）
from app.models.flow import (  # 协作流程 BOM/成本卡片（注册 metadata 供 create_all 建表）
    OpportunityFlow,
    OpportunityFlowNode,
    OpportunityRequirement,
    OpportunityBomScheme,
    OpportunityCostSheet,
    OpportunityFlowCard,
    OpportunityFlowCardLink,
    FlowAssignmentRule,
)
from app.models.role import Role  # RBAC 角色（注册 metadata 供 create_all 建表）
from app.repository.rules_repo import RulesRepository
from app.repository.system_config_repo import SystemConfigRepository
import json


def ensure_parts_master_columns():
    """料号库字段语义重构（幂等迁移，boot 时自愈）：
    原 description 列存的是自由文本规格串 → 重命名为 spec_text（UI label「规格」）；
    新增 description 列装人话用途说明（UI label「说明」）。存量数据无损落入 spec_text。
    major_category（大类·一级导航）也在此建列，SSOT=l6.part_taxonomy（见 create_part_taxonomy.sql）。"""
    from app.models.base import l6_engine
    from sqlalchemy import text
    with l6_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='l6' AND table_name='parts_master'"
        ))}
    if "spec_text" not in cols and "description" in cols:
        with l6_engine.begin() as c:
            c.execute(text("ALTER TABLE l6.parts_master RENAME COLUMN description TO spec_text"))
        cols.discard("description"); cols.add("spec_text")
    if "description" not in cols:
        with l6_engine.begin() as c:
            c.execute(text("ALTER TABLE l6.parts_master ADD COLUMN description TEXT"))
    if "major_category" not in cols:
        with l6_engine.begin() as c:
            c.execute(text("ALTER TABLE l6.parts_master ADD COLUMN major_category TEXT"))


def ensure_base_config_linkage_columns():
    """机型↔基准配置 一对多关联（幂等迁移，boot 时自愈）：
    base_configs 加 model_id（反向关联机型，ON DELETE SET NULL）+ config_content（配置级介绍 JSONB）。
    回填把「已被机型 base_config_id 挂载」的配置补上 model_id——纯数据派生，零业务名硬编码；
    孤儿配置（未被任何机型挂载）保持 NULL，由用户在机型编辑页手动归属（可随时改）。
    对应 migrations/add_model_link_to_base_configs.sql。"""
    from app.models.base import l6_engine
    from sqlalchemy import text
    with l6_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='l6' AND table_name='base_configs'"
        ))}
    with l6_engine.begin() as c:
        if "model_id" not in cols:
            c.execute(text(
                "ALTER TABLE l6.base_configs ADD COLUMN model_id INTEGER "
                "REFERENCES l6.server_models(id) ON DELETE SET NULL"
            ))
        if "config_content" not in cols:
            c.execute(text("ALTER TABLE l6.base_configs ADD COLUMN config_content JSONB"))
        # 反向回填（幂等：仅填 model_id 为 NULL 且被某机型挂载的；孤儿不动）
        c.execute(text("""
            UPDATE l6.base_configs bc
            SET model_id = (SELECT id FROM l6.server_models sm WHERE sm.base_config_id = bc.id)
            WHERE bc.model_id IS NULL
              AND EXISTS (SELECT 1 FROM l6.server_models sm WHERE sm.base_config_id = bc.id)
        """))
        # base_config_id 允许空：新建机型可先无主配置，关联配置后再设主（去掉旧 NOT NULL）
        c.execute(text("ALTER TABLE l6.server_models ALTER COLUMN base_config_id DROP NOT NULL"))
        c.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_base_configs_model_id ON l6.base_configs(model_id)"
        ))


def ensure_base_config_constraint_columns():
    """基准配置「机箱能力约束」字段（幂等 DDL，boot 时自愈）：
    base_configs 加 psu_wattages（允许的 PSU 瓦数档位 JSONB，如 [1300,1600,2000]；
    NULL=不限沿用全局档位）、max_cpu（CPU 颗数上限，默认 2）、max_dimm（内存条数上限，默认 24）、
    mem_channels（每路内存通道数，默认 12，EPYC 12ch/路，驱动内存选型目标条数）。
    全部在基准配置页「机箱能力」可配，缺省用兜底默认——拒绝把机型物理边界散落硬编码。"""
    from app.models.base import l6_engine
    from sqlalchemy import text
    with l6_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='l6' AND table_name='base_configs'"
        ))}
    with l6_engine.begin() as c:
        if "psu_wattages" not in cols:
            c.execute(text("ALTER TABLE l6.base_configs ADD COLUMN psu_wattages JSONB"))
        if "max_cpu" not in cols:
            c.execute(text("ALTER TABLE l6.base_configs ADD COLUMN max_cpu INTEGER NOT NULL DEFAULT 2"))
        if "max_dimm" not in cols:
            c.execute(text("ALTER TABLE l6.base_configs ADD COLUMN max_dimm INTEGER NOT NULL DEFAULT 24"))
        if "mem_channels" not in cols:
            c.execute(text("ALTER TABLE l6.base_configs ADD COLUMN mem_channels INTEGER NOT NULL DEFAULT 12"))


def ensure_server_model_published_column():
    """机型「是否上架」开关（幂等 DDL，boot 时自愈）：
    server_models 加 is_published BOOLEAN NOT NULL DEFAULT TRUE（存量机型全部视为已上架）。
    下架机型只在面向客户的服务器货架（机型目录）隐藏；管理面/报价/推理流照旧可见。"""
    from app.models.base import l6_engine
    from sqlalchemy import text
    with l6_engine.begin() as c:
        c.execute(text(
            "ALTER TABLE l6.server_models "
            "ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT TRUE"
        ))


def ensure_assistant_reasoning_columns():
    """方案助手需求分析通道（幂等 DDL，boot 时自愈）：
    assistant_threads 加 reasoning_state（需求分析会话状态 JSON）与
    thread_kind（assistant=方案助手全局会话 / office_colleague=AI Office 同事会话）；
    assistant_messages 加 kind（消息类型）+ data（结构化载荷，如方案列表）
    + colleague_role_key（群聊式头像/昵称展示）。
    对应 create_assistant_tables.sql 的扩展——旧库 ADD COLUMN，新库由 ORM create_all 直接带列。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        t_cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='assistant_threads'"
        ))}
        m_cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='assistant_messages'"
        ))}
    with opp_engine.begin() as c:
        if "reasoning_state" not in t_cols:
            c.execute(text("ALTER TABLE opportunities.assistant_threads ADD COLUMN reasoning_state TEXT"))
        if "thread_kind" not in t_cols:
            c.execute(text("ALTER TABLE opportunities.assistant_threads ADD COLUMN thread_kind TEXT NOT NULL DEFAULT 'assistant'"))
        if "colleague_role_key" not in t_cols:
            c.execute(text("ALTER TABLE opportunities.assistant_threads ADD COLUMN colleague_role_key TEXT"))
        if "kind" not in m_cols:
            c.execute(text("ALTER TABLE opportunities.assistant_messages ADD COLUMN kind TEXT DEFAULT 'text'"))
        if "data" not in m_cols:
            c.execute(text("ALTER TABLE opportunities.assistant_messages ADD COLUMN data TEXT"))
        if "colleague_role_key" not in m_cols:
            c.execute(text("ALTER TABLE opportunities.assistant_messages ADD COLUMN colleague_role_key TEXT"))
        if "thread_kind" not in t_cols:
            c.execute(text(
                "UPDATE opportunities.assistant_threads t "
                "SET thread_kind='office_colleague' "
                "WHERE EXISTS (SELECT 1 FROM opportunities.assistant_messages m "
                "WHERE m.thread_id=t.thread_id AND m.kind='opening' "
                "AND m.colleague_role_key IS NOT NULL AND m.colleague_role_key <> 'assistant')"
            ))
        if "colleague_role_key" not in t_cols:
            c.execute(text(
                "UPDATE opportunities.assistant_threads t "
                "SET colleague_role_key=m.colleague_role_key "
                "FROM opportunities.assistant_messages m "
                "WHERE m.thread_id=t.thread_id AND m.kind='opening' "
                "AND m.colleague_role_key IS NOT NULL AND m.colleague_role_key <> 'assistant'"
            ))



def ensure_assistant_preview_office_index():
    """允许 Skill 预览线程与正式 office 线程共存：唯一索引排除 entry_point=skill_studio_preview。"""
    from sqlalchemy import text
    try:
        with opp_engine.begin() as c:
            c.execute(text("DROP INDEX IF EXISTS opportunities.uq_assistant_office_thread_active"))
            c.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_assistant_office_thread_active "
                "ON opportunities.assistant_threads (created_by, colleague_role_key) "
                "WHERE thread_kind='office_colleague' AND colleague_role_key IS NOT NULL "
                "AND deleted_at IS NULL AND entry_point IS DISTINCT FROM 'skill_studio_preview'"
            ))
        print("✅ Assistant preview office index ensured")
    except Exception as e:
        print(f"⚠️ Assistant preview office index ensure failed: {e}")

def ensure_compatibility_rule_category():
    """兼容规则加「业务分类」列（幂等 DDL，boot 时自愈）：
    rules.compatibility_rules 加 category TEXT + 索引。用户可自定义的开放标签，引擎不感知。
    存量行的 NULL 回填由 repo.backfill_default_categories() 按 name→category 完成（数据层）。"""
    from app.models.base import rules_engine
    from sqlalchemy import text
    with rules_engine.begin() as c:
        c.execute(text(
            "ALTER TABLE rules.compatibility_rules ADD COLUMN IF NOT EXISTS category TEXT"
        ))
        c.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_compat_rules_category "
            "ON rules.compatibility_rules(category)"
        ))



def ensure_compatibility_rule_regions():
    """兼容规则加「显式绑定区域大类」列（幂等 DDL，boot 时自愈）：
    rules.compatibility_rules 加 regions TEXT（JSON 数组：料号库大类 id 列表）。
    绑定粒度为「区域类型=料号库大类」——机型无关、不随图纸版本失效。"""
    from app.models.base import rules_engine
    from sqlalchemy import text
    with rules_engine.begin() as c:
        c.execute(text(
            "ALTER TABLE rules.compatibility_rules ADD COLUMN IF NOT EXISTS regions TEXT"
        ))


def ensure_feed_user_auth_columns():
    """feed_users 加认证列（幂等 DDL，boot 时自愈）：
    password_hash（bcrypt 哈希，空=旧身份未设密码）+ is_active（禁用标记）。
    旧库 ADD COLUMN；新库由 ORM create_all 直接带列。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='feed_users'"
        ))}
    with opp_engine.begin() as c:
        if "password_hash" not in cols:
            c.execute(text("ALTER TABLE opportunities.feed_users ADD COLUMN password_hash TEXT"))
        if "is_active" not in cols:
            c.execute(text("ALTER TABLE opportunities.feed_users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))


def ensure_feed_message_node_key():
    """评论挂到审批节点（幂等 DDL，boot 时自愈）：
    opportunities.opportunity_messages 加 node_key，允许评论归属到具体流程节点。
    旧评论 node_key 为空，前端回退到 requirement 节点展示。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='opportunity_messages'"
        ))}
    with opp_engine.begin() as c:
        if "node_key" not in cols:
            c.execute(text("ALTER TABLE opportunities.opportunity_messages ADD COLUMN node_key TEXT"))


def ensure_opportunity_owner_column():
    """商机归属列（幂等 DDL，boot 时自愈）：
    opportunities.opportunities 加 owner_user_id，记录创建商机的登录用户。
    存量行先为 NULL，等销售账号同步后再回填。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='opportunities'"
        ))}
    with opp_engine.begin() as c:
        if "owner_user_id" not in cols:
            c.execute(text("ALTER TABLE opportunities.opportunities ADD COLUMN owner_user_id TEXT"))


def drop_pet_settings_column():
    """清理旧桌宠设置死列（幂等 DDL，boot 时自愈）：
    opportunities.feed_users.pet_settings 已被「按 AI 同事角色统一形象」取代，
    ORM/启动/前端均已无引用；旧数据（每账号 default_model/by_role）按方案有意丢弃。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='feed_users'"
        ))}
    with opp_engine.begin() as c:
        if "pet_settings" in cols:
            c.execute(text("ALTER TABLE opportunities.feed_users DROP COLUMN pet_settings"))


def ensure_quotation_submission_columns():
    """报价单发送状态（幂等 DDL，boot 时自愈）：
    opportunities.quotations 加 submitted_at / submitted_by / submitted_attachment_id。
    只有报价员正式发送并推送 Excel 到报价审批评论后才会写入 submitted_at。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='quotations'"
        ))}
    with opp_engine.begin() as c:
        if "submitted_at" not in cols:
            c.execute(text("ALTER TABLE opportunities.quotations ADD COLUMN submitted_at TEXT"))
        if "submitted_by" not in cols:
            c.execute(text("ALTER TABLE opportunities.quotations ADD COLUMN submitted_by TEXT"))
        if "submitted_attachment_id" not in cols:
            c.execute(text("ALTER TABLE opportunities.quotations ADD COLUMN submitted_attachment_id TEXT"))


def ensure_quotation_config_relation_columns():
    """报价单配置关系（幂等 DDL，boot 时自愈）：
    opportunities.quotations 加 config_relation（compose/alternative）与 primary_config（主推配置名）。
    方案备选模式（alternative）下配置不求和，total_qty 取需求台数。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='quotations'"
        ))}
    with opp_engine.begin() as c:
        if "config_relation" not in cols:
            c.execute(text("ALTER TABLE opportunities.quotations ADD COLUMN config_relation TEXT DEFAULT 'compose'"))
        if "primary_config" not in cols:
            c.execute(text("ALTER TABLE opportunities.quotations ADD COLUMN primary_config TEXT DEFAULT ''"))


def ensure_bom_scheme_config_relation_columns():
    """BOM 方案配置关系（幂等 DDL，boot 时自愈）：
    opportunities.opportunity_bom_schemes 加 config_relation（compose/alternative）与 primary_config（主推配置名）。
    方案配置从需求单继承默认模式，本方案可独立修改，不回写需求单。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='opportunities' AND table_name='opportunity_bom_schemes'"
        ))}
    with opp_engine.begin() as c:
        if "config_relation" not in cols:
            c.execute(text("ALTER TABLE opportunities.opportunity_bom_schemes ADD COLUMN config_relation TEXT DEFAULT 'compose'"))
        if "primary_config" not in cols:
            c.execute(text("ALTER TABLE opportunities.opportunity_bom_schemes ADD COLUMN primary_config TEXT DEFAULT ''"))


def backfill_premature_done_flows():
    """回退旧逻辑误置的 done 流程：当前在报价节点、状态为 done，
    但没有任何已发送报价单（submitted_at IS NULL）→ 重置为 running，等待报价员真正发送。"""
    from app.models.base import opp_engine
    from sqlalchemy import text
    with opp_engine.begin() as c:
        c.execute(text("""
            UPDATE opportunities.opportunity_flows f
            SET status = 'running'
            WHERE f.status = 'done'
              AND f.current_node = 'quoting'
              AND NOT EXISTS (
                  SELECT 1
                  FROM opportunities.quotations q
                  WHERE q.opportunity_id = f.opportunity_id
                    AND q.submitted_at IS NOT NULL
              )
        """))


_DEFAULT_PERMISSIONS = [
    {"key": "page.portal", "name": "工作台", "group": "page", "module": "工作台"},
    {"key": "page.opportunities", "name": "商机线索", "group": "page", "module": "商机线索"},
    {"key": "page.opportunities_all", "name": "商机线索·全量视图", "group": "page", "module": "商机线索"},
    {"key": "page.servers", "name": "服务器", "group": "page", "module": "服务器"},
    {"key": "page.parts", "name": "配件", "group": "page", "module": "配件"},
    {"key": "page.strategies", "name": "策略中心", "group": "page", "module": "策略中心"},
    {"key": "ai.office.manage", "name": "AI 员工与空间管理", "group": "action", "module": "AI 办公室"},
    {"key": "ai.office.admin", "name": "AI 运行与管理", "group": "action", "module": "AI 办公室"},
    {"key": "page.settings.excel", "name": "解析规则", "group": "page", "module": "设置"},
    {"key": "page.settings.templates", "name": "导出模板", "group": "page", "module": "设置"},
    {"key": "page.settings.admin", "name": "服务器管理", "group": "page", "module": "设置"},
    {"key": "page.settings.users", "name": "用户与权限", "group": "page", "module": "设置"},
    {"key": "field.quote.price", "name": "报价工作台·价格", "group": "field", "module": "工作台"},
    {"key": "field.opportunity.quote_price", "name": "商机详情·报价单价格", "group": "field", "module": "商机线索"},
    {"key": "field.parts.price", "name": "配件页·价格", "group": "field", "module": "配件"},
    {"key": "field.flow.bom", "name": "流程·中间BOM交付物", "group": "field", "module": "商机线索"},
    {"key": "field.flow.cost", "name": "流程·成本核价交付物", "group": "field", "module": "商机线索"},
    {"key": "action.flow.return.boming", "name": "退回方案配置", "group": "action", "module": "商机线索"},
    {"key": "action.flow.return.costing", "name": "退回成本核算", "group": "action", "module": "商机线索"},
    {"key": "action.flow.return.quoting", "name": "退回市场报价", "group": "action", "module": "商机线索"},
    {"key": "action.flow.submit.quoting", "name": "发送报价单", "group": "action", "module": "商机线索"},
]

_REMOVED_PERMISSION_KEYS = {"field.server.price"}


def ensure_permission_catalog():
    """权限目录种子（幂等，只补缺失 key，不覆盖用户已有配置）。"""
    from app.repository.system_config_repo import SystemConfigRepository
    repo = SystemConfigRepository()
    try:
        catalog = repo.get_value("auth.permissions", None)
        if catalog is None:
            catalog = _DEFAULT_PERMISSIONS
        elif not isinstance(catalog, list):
            catalog = []
        changed = False
        filtered_catalog = []
        for item in catalog:
            if isinstance(item, dict) and item.get("key") in _REMOVED_PERMISSION_KEYS:
                changed = True
                continue
            filtered_catalog.append(item)
        if changed:
            catalog = filtered_catalog
        existing_keys = {p.get("key") for p in catalog if isinstance(p, dict) and p.get("key")}
        default_by_key = {item["key"]: item for item in _DEFAULT_PERMISSIONS}
        for item in catalog:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            default = default_by_key.get(item["key"])
            if default:
                item.setdefault("module", default["module"])
                item.setdefault("group", default["group"])
        for item in _DEFAULT_PERMISSIONS:
            if item.get("key") not in existing_keys:
                catalog.append(item)
                changed = True
        if catalog is not _DEFAULT_PERMISSIONS or changed:
            repo.set("auth.permissions", catalog, type="json", description="权限目录")
        print("✅ Permission catalog ensured (auth.permissions)")
    finally:
        repo.close()


def ensure_roles_table_and_seed():
    """角色种子（幂等，仅空表时写入一次）：rules.roles。
    admin 特殊（权限=目录全量）；其余角色为初始建议值，页面可改可增。"""
    from app.repository.role_repo import RoleRepository
    repo = RoleRepository()
    try:
        n = repo.seed_defaults()
        if n:
            print(f"✅ Roles seeded ({n} default roles)")
        m = repo.seed_missing_defaults()
        if m:
            print(f"✅ Role permissions backfilled ({m} roles)")
        removed = repo.prune_removed_permissions()
        if removed:
            print(f"✅ Removed obsolete permissions from {removed} roles")
    finally:
        repo.close()


def ensure_bootstrap_admin():
    """引导管理员（幂等，boot 时自愈；绝不每次重启重置密码）：
    - 已有「带密码的 admin 角色用户」→ 不动（密码保持，避免重启漂移）；
    - 有 admin 角色但密码为空（旧身份）→ 设随机密码并打印一次；
    - 无 admin 角色 → 创建 admin（随机密码打印一次）。
    之后密码由管理员在「用户与权限」页修改。"""
    import secrets
    from app.repository.feed_user_repo import FeedUserRepository
    from app.core.security import hash_password
    repo = FeedUserRepository()
    try:
        existing = repo.get_by_name_auth("admin")
        if existing and existing.get("role") == "admin" and existing.get("password_hash"):
            return  # 已有可用管理员，不重置
        password = secrets.token_urlsafe(12)
        if not existing:
            repo.create_user(name="admin", role="admin", password_hash=hash_password(password))
        else:
            repo.update_role(existing["user_id"], "admin")
            repo.update_active(existing["user_id"], True)
            repo.set_password(existing["user_id"], hash_password(password))
        print(f"🚀 引导管理员：admin / {password}（登录后请立即在「用户与权限」修改密码）")
    finally:
        repo.close()


def backfill_bom_schemes_from_quotations():
    """一次性历史迁移：把尚无流程实体的旧报价单回填为 BOM/成本卡片。

    仅处理「既没有 BOM 方案、也没有成本表」的商机；已有任一流程实体时跳过，
    避免把下游报价单反向生成为上游成本表。该函数不再在每次启动时自动运行，
    应由显式迁移脚本按需执行。
    """
    from datetime import datetime
    from app.models.flow import OpportunityBomScheme, OpportunityCostSheet
    from app.models.quotation import Quotation
    from app.models.quotation_item import QuotationItem
    from app.models.base import Opportunity_SessionLocal

    db = Opportunity_SessionLocal()
    created = 0
    skipped = 0
    try:
        opp_rows = db.query(Quotation.opportunity_id).filter(
            Quotation.status == "active",
            Quotation.source.in_(["worktable", "manual"]),
        ).distinct().all()
        for (opp_id,) in opp_rows:
            existing = db.query(OpportunityBomScheme).filter(
                OpportunityBomScheme.opportunity_id == opp_id
            ).first()
            existing_sheet = db.query(OpportunityCostSheet).filter(
                OpportunityCostSheet.opportunity_id == opp_id
            ).first()
            if existing or existing_sheet:
                skipped += 1
                continue
            quote = db.query(Quotation).filter(
                Quotation.opportunity_id == opp_id,
                Quotation.status == "active",
            ).order_by(Quotation.exported_at.desc(), Quotation.created_at.desc()).first()
            if not quote:
                continue

            items = db.query(QuotationItem).filter(
                QuotationItem.quotation_id == quote.quotation_id
            ).all()
            extra = {}
            if quote.extra_fields:
                try:
                    extra = json.loads(quote.extra_fields) or {}
                except (json.JSONDecodeError, TypeError):
                    extra = {}
            picks = extra.get("config_l6_picks") or {}
            if not isinstance(picks, dict):
                picks = {}

            names = list((quote.config_quantities or {}).keys())
            if not names:
                names = sorted({it.config_name for it in items if it.config_name})
            if not names:
                names = ["CFG1"]

            configs = []
            for name in names:
                pick = picks.get(name) or {}
                if not isinstance(pick, dict):
                    pick = {}
                l6_rows = [
                    {
                        "category": "L6",
                        "catalogue": row.get("catalogue") or "",
                        "description": row.get("description") or "",
                        "part_category": row.get("part_category") or "",
                        "qty": int(row.get("qty") or 0),
                        "base_price": row.get("base_price") or 0,
                        "final_price": row.get("final_price") or 0,
                        "profit_margin": row.get("profit_margin") or 0,
                        "currency": "RMB",
                        "note": row.get("note") or "",
                    }
                    for row in (pick.get("bom_excel_rows") or [])
                    if isinstance(row, dict) and (row.get("category") or "") in ("L6", "整机")
                ]
                kp_rows = []
                for it in items:
                    if it.config_name != name or (it.category or "") != "Key Parts":
                        continue
                    it_extra = {}
                    if it.extra_fields:
                        try:
                            it_extra = json.loads(it.extra_fields) or {}
                        except (json.JSONDecodeError, TypeError):
                            it_extra = {}
                    kp_rows.append({
                        "item_id": it.item_id,
                        "category": "Key Parts",
                        "part_category": it.part_category or "",
                        "catalogue": it.catalogue or "",
                        "description": it.description or "",
                        "qty": it.qty or 0,
                        "base_price": it.base_price or 0,
                        "final_price": it.final_price or 0,
                        "profit_margin": it.profit_margin or 0,
                        "currency": it.currency or "RMB",
                        "note": it_extra.get("note") or "",
                    })
                l6_cost = float(pick.get("l6_custom_price") or 0) if pick.get("l6_price_manual") else 0
                configs.append({
                    "name": name,
                    "server_model": (quote.config_server_models or {}).get(name) or "",
                    "description": (quote.config_descriptions or {}).get(name) or "",
                    "qty": int((quote.config_quantities or {}).get(name) or 1),
                    "l6_cost": l6_cost,
                    "l6_margin": 0,
                    "l6_rows": l6_rows,
                    "kp_rows": kp_rows,
                    "totals": {},
                })

            if not configs:
                continue
            now = datetime.now().isoformat()
            scheme = OpportunityBomScheme(
                opportunity_id=opp_id,
                name=f"存量-{quote.quotation_name or quote.quotation_id[:8]}",
                status="current",
                configs=configs,
                created_by=quote.submitted_by or "system",
                created_at=quote.created_at or now,
                updated_at=quote.updated_at or now,
            )
            db.add(scheme)
            db.flush()

            sheet = OpportunityCostSheet(
                opportunity_id=opp_id,
                bom_scheme_id=scheme.id,
                name=f"成本-{scheme.name}",
                status="current" if quote.cost_snapshot else "draft",
                configs=json.loads(json.dumps(configs)),
                quotation_id=quote.quotation_id,
                created_by=quote.submitted_by or "system",
                created_at=quote.created_at or now,
                updated_at=quote.updated_at or now,
            )
            db.add(sheet)
            created += 1
        db.commit()
        return {"created": created, "skipped": skipped}
    finally:
        db.close()


def repair_bom_scheme_l6_rows():
    """清理历史回填错误：误混进 BOM/成本表 l6_rows 的 KP 行。

    旧版 backfill_bom_schemes_from_quotations 会把 bom_excel_rows 的 L6+KP 平铺行
    全部写入 configs[].l6_rows。KP 行的特征是 part_category 有值；L6 行该字段始终为空。
    """
    from app.models.flow import OpportunityBomScheme, OpportunityCostSheet
    from app.models.base import Opportunity_SessionLocal

    db = Opportunity_SessionLocal()
    try:
        for model in (OpportunityBomScheme, OpportunityCostSheet):
            rows = db.query(model).filter(model.configs.isnot(None)).all()
            for row in rows:
                configs = row.configs or []
                changed = False
                cleaned = []
                for cfg in configs:
                    if not isinstance(cfg, dict):
                        cleaned.append(cfg)
                        continue
                    l6_rows = cfg.get("l6_rows") or []
                    if not isinstance(l6_rows, list):
                        cleaned.append(cfg)
                        continue
                    next_rows = [r for r in l6_rows if isinstance(r, dict) and not (r.get("part_category") or "")]
                    if len(next_rows) != len(l6_rows):
                        cfg = dict(cfg)
                        cfg["l6_rows"] = next_rows
                        changed = True
                    cleaned.append(cfg)
                if changed:
                    row.configs = cleaned
                    db.add(row)
        db.commit()
    finally:
        db.close()


def ensure_reasoning_skill_key_column():
    """给 rules.reasoning_flow 增加正式 skill_key 关联并回填存量同名行（幂等）。

    旧库只用 name 充当 workflow_key；新库优先 skill_key，name 保留兼容展示/历史。
    """
    from sqlalchemy import text
    with rules_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='rules' AND table_name='reasoning_flow'"
        ))}
    if not cols:
        return
    with rules_engine.begin() as c:
        if "skill_key" not in cols:
            c.execute(text("ALTER TABLE rules.reasoning_flow ADD COLUMN skill_key VARCHAR(80)"))
        c.execute(text(
            "UPDATE rules.reasoning_flow SET skill_key = name "
            "WHERE skill_key IS NULL AND name IS NOT NULL"
        ))


def ensure_skill_catalog_approval_policy_dropped():
    """移除 Skill 级 approval_policy（草稿语义改由输出物承担）。

    新库由 ORM create_all 直接不带该列；旧库这里幂等 DROP COLUMN。
    """
    from sqlalchemy import text
    with rules_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='rules' AND table_name='skill_catalog'"
        ))}
    if "approval_policy" not in cols:
        return
    with rules_engine.begin() as c:
        c.execute(text("ALTER TABLE rules.skill_catalog DROP COLUMN approval_policy"))


def ensure_skill_catalog_routing_columns():
    """skill_catalog 只保留 hit_count；清理已废弃的 trigger_rules 列（幂等）。"""
    from sqlalchemy import text
    with rules_engine.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='rules' AND table_name='skill_catalog'"
        ))}
    if not cols:
        return
    with rules_engine.begin() as c:
        if "trigger_rules" in cols:
            c.execute(text("ALTER TABLE rules.skill_catalog DROP COLUMN trigger_rules"))
        if "hit_count" not in cols:
            c.execute(text("ALTER TABLE rules.skill_catalog ADD COLUMN hit_count INTEGER NOT NULL DEFAULT 0"))
        c.execute(text("UPDATE rules.skill_catalog SET hit_count = 0 WHERE hit_count IS NULL"))


def ensure_excel_parser_region_model():
    """Excel 解析规则：为 parse_regions/parse_field_rules 增加系统化列并回填（幂等）。"""
    from sqlalchemy import text
    statements = [
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS region_key VARCHAR(80)",
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS region_type VARCHAR(20) NOT NULL DEFAULT 'dynamic'",
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS enabled INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS start_mode VARCHAR(20) NOT NULL DEFAULT 'keyword'",
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS end_mode VARCHAR(20) NOT NULL DEFAULT 'eof'",
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS start_config TEXT",
        "ALTER TABLE rules.parse_regions ADD COLUMN IF NOT EXISTS end_config TEXT",
        "ALTER TABLE rules.parse_field_rules ADD COLUMN IF NOT EXISTS region_id INTEGER",
    ]
    with rules_engine.begin() as c:
        for statement in statements:
            c.execute(text(statement))
        c.execute(text("UPDATE rules.parse_regions SET region_key = lower(name) WHERE region_key IS NULL"))
        c.execute(text("UPDATE rules.parse_regions SET region_type = 'static' WHERE lower(name) = 'header' AND (region_type IS NULL OR region_type = '')"))
        c.execute(text("UPDATE rules.parse_regions SET region_type = 'dynamic' WHERE region_type IS NULL OR region_type = ''"))
        c.execute(text("UPDATE rules.parse_regions SET enabled = 1 WHERE enabled IS NULL"))
        c.execute(text(
            "UPDATE rules.parse_field_rules f SET region_id = r.id "
            "FROM rules.parse_regions r "
            "WHERE lower(f.region) = lower(r.name) AND f.region_id IS NULL"
        ))
        c.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_parse_regions_region_key "
            "ON rules.parse_regions(region_key) WHERE region_key IS NOT NULL"
        ))

def cleanup_legacy_skill_library_mirror():
    """删除 system_config.ai_colleagues.skill_library JSON 镜像；Skill 定义只保留 rules.skill_catalog。"""
    repo = SystemConfigRepository()
    try:
        cfg = repo.get_value("ai_colleagues", {}) or {}
        if not isinstance(cfg, dict) or "skill_library" not in cfg:
            return
        cfg.pop("skill_library", None)
        repo.set("ai_colleagues", cfg, "json", "AI 同事配置（Skill 定义统一由 rules.skill_catalog 管理）", "system")
    finally:
        repo.close()


def init_rules_db():
    """Create rules database tables and initialize default rules if empty."""
    # Create all tables for rules DB
    Base.metadata.create_all(bind=rules_engine)
    # Create tables for L6 history DB
    Base.metadata.create_all(bind=l6_history_engine)
    # Create tables for opportunities DB (includes spec_templates)
    Base.metadata.create_all(bind=opp_engine)

    # 旧库迁移：reasoning_flow 增加 skill_key 列并回填。
    try:
        ensure_reasoning_skill_key_column()
    except Exception as e:
        print(f"⚠️ Reasoning flow skill_key migration failed: {e}")
    try:
        ensure_skill_catalog_approval_policy_dropped()
    except Exception as e:
        print(f"⚠️ Skill catalog approval_policy cleanup failed: {e}")
    try:
        ensure_skill_catalog_routing_columns()
    except Exception as e:
        print(f"⚠️ Skill catalog routing columns migration failed: {e}")
    
    try:
        ensure_excel_parser_region_model()
    except Exception as e:
        print(f"⚠️ Excel parser region model migration failed: {e}")

    # Initialize default rules if empty
    rules_repo = RulesRepository()

    # --- KP Category Mappings ---
    kp_mappings = rules_repo.get_kp_category_mappings()
    if not kp_mappings:
        default_kp_mappings = [
            {"keyword": "cpu", "category": "CPU", "priority": 1},
            {"keyword": "processor", "category": "CPU", "priority": 2},
            {"keyword": "memory", "category": "Memory", "priority": 1},
            {"keyword": "ram", "category": "Memory", "priority": 2},
            {"keyword": "hdd", "category": "HDD/SSD", "priority": 1},
            {"keyword": "ssd", "category": "HDD/SSD", "priority": 2},
            {"keyword": "raid", "category": "Raid card", "priority": 1},
            {"keyword": "network", "category": "NIC", "priority": 1},
            {"keyword": "nic", "category": "NIC", "priority": 2},
            {"keyword": "gpu", "category": "GPU", "priority": 1},
            {"keyword": "power", "category": "Power", "priority": 1},
            {"keyword": "psu", "category": "Power", "priority": 2},
            {"keyword": "fan", "category": "Fan", "priority": 1},
            {"keyword": "heatsink", "category": "Heatsink", "priority": 1},
            {"keyword": "cooler", "category": "Heatsink", "priority": 2},
            {"keyword": "cable", "category": "Cable", "priority": 1},
            {"keyword": "wire", "category": "Cable", "priority": 2},
            {"keyword": "rail", "category": "Rail", "priority": 1},
        ]
        for mapping in default_kp_mappings:
            rules_repo.add_kp_category_mapping(mapping)
    
    print("✅ Rules database initialized")

    # system_config 无启动种子（2026-09-02 定调：DB 是唯一来源，代码不存默认值）。
    # 技能提示词 & 推理节点默认契约 → DB 唯一权威（空库播种；运行后只读新表，无种子/兜底）
    try:
        from app.services.skill_config_bootstrap import ensure_skill_prompt_templates, ensure_reasoning_node_defaults
        _pn = ensure_skill_prompt_templates()
        _nd = ensure_reasoning_node_defaults()
        if _pn or _nd:
            print(f"✅ Skill config bootstrapped (prompts {_pn}, node_defaults {_nd})")
        else:
            print("✅ Skill config already seeded in DB")
    except Exception as e:
        print(f"⚠️ Skill config bootstrap failed: {e}")

    try:
        cleanup_legacy_skill_library_mirror()
        print("✅ Legacy skill_library mirror cleaned")
    except Exception as e:
        print(f"⚠️ Legacy skill_library mirror cleanup failed: {e}")

    # Reasoning flow default seed + business graph migrate
    try:
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        rf_repo = ReasoningFlowRepository()
        try:
            # 首次部署建默认流；已有流则不动。
            rf_repo.seed_default_if_empty()
        finally:
            rf_repo.close()
    except Exception as e:
        print(f"⚠️ Reasoning flow init failed: {e}")

    # Capability spec 启动自检：prompt/工具引用在源存在，避免“用了但没定义”运行期崩溃。
    try:
        from app.services import capability_spec
        errors = capability_spec.validate_specs()
        if errors:
            for e in errors:
                print(f"⚠️ Capability spec validation: {e}")
        else:
            print("✅ Capability spec validated（prompt/tool 引用全部在源）")
    except Exception as e:
        print(f"⚠️ Capability spec validation failed: {e}")


    # 兼容规则分类列 DDL（必须在 ORM seed/backfill 前跑，确保列存在）
    try:
        ensure_compatibility_rule_category()
        ensure_compatibility_rule_regions()
    except Exception as e:
        print(f"⚠️ Compatibility rule category column init failed: {e}")

    # Compatibility rules default seed (兼容性规则引擎：require/exclude/derive/filter/recommend)
    try:
        from app.repository.compatibility_rule_repo import CompatibilityRuleRepository
        cr_repo = CompatibilityRuleRepository()
        try:
            n = cr_repo.seed_default_if_empty()
            if n:
                print(f"✅ Compatibility rules initialized ({n} rules)")
            else:
                print("✅ Compatibility rules already present")
            # 按名补种 DEFAULT_RULES 新增项（不覆盖用户已有改动）
            m = cr_repo.seed_missing_defaults()
            if m:
                print(f"   + {m} new default rule(s) appended (non-destructive)")
            # 按 name→category 给存量规则回填默认分类（新增列后老规则该列为 NULL）
            b = cr_repo.backfill_default_categories()
            if b:
                print(f"   + {b} rule(s) categorized by default")
        finally:
            cr_repo.close()
    except Exception as e:
        print(f"⚠️ Compatibility rules init failed: {e}")

    # BOM案例库：独立表（rules.bom_cases，无数字 id，时间戳业务键；kp_lines 只引用 kp_parts）。
    try:
        from app.services.case_library_init import ensure_bom_cases_table
        ensure_bom_cases_table()
        print("✅ BOM案例库 ensured")
    except Exception as e:
        print(f"⚠️ BOM案例库 init failed: {e}")

    # Ensure comments table exists (raw SQL table on public schema, no ORM model)
    try:
        from app.repository.comment_repo import ensure_comments_table
        ensure_comments_table()
        print("✅ Comments table ensured")
    except Exception as e:
        print(f"⚠️ Comments table init failed: {e}")

    # 需求分析：CPU/GPU 型号家族词表自动补齐（从 kp 库件名抽取新型号，只加不删）
    try:
        from app.services.model_family_sync import sync_model_family_words
        n = sync_model_family_words()
        if n:
            print(f"   🧬 model_family_words +{n} 个型号词（kp 库自动补齐）")
    except Exception as e:
        print(f"⚠️ model_family_words sync failed: {e}")

    # 料号库字段语义重构：原 description(规格串) → spec_text，新增 description(说明)
    try:
        ensure_parts_master_columns()
        print("✅ Parts master columns ensured (spec_text/description)")
    except Exception as e:
        print(f"⚠️ Parts master migrate failed: {e}")

    # 机型↔基准配置 一对多：base_configs 加 model_id + config_content，回填归属
    try:
        ensure_base_config_linkage_columns()
        print("✅ Base config linkage columns ensured (model_id/config_content)")
    except Exception as e:
        print(f"⚠️ Base config linkage migrate failed: {e}")

    # 基准配置「机箱能力约束」：PSU 档位 / CPU 上限 / 内存条数上限 / 每路通道数（可配，拒绝硬编码）
    try:
        ensure_base_config_constraint_columns()
        print("✅ Base config constraint columns ensured (psu_wattages/max_cpu/max_dimm/mem_channels)")
    except Exception as e:
        print(f"⚠️ Base config constraint migrate failed: {e}")

    # 机型「是否上架」：下架机型不进服务器货架（机型目录），管理面/工作台照旧全量
    try:
        ensure_server_model_published_column()
        print("✅ Server model published column ensured (is_published)")
    except Exception as e:
        print(f"⚠️ Server model published migrate failed: {e}")

    # 方案助手需求分析通道：assistant_threads.reasoning_state + assistant_messages.kind/data
    try:
        ensure_assistant_reasoning_columns()
        ensure_assistant_preview_office_index()
        print("✅ Assistant reasoning columns ensured (reasoning_state/thread_kind/kind/data/colleague_role_key)")
    except Exception as e:
        print(f"⚠️ Assistant reasoning columns migrate failed: {e}")

    # 认证：feed_users 加 password_hash/is_active 列 + 引导管理员（幂等，仅首次有效）
    try:
        ensure_feed_user_auth_columns()
        print("✅ Feed user auth columns ensured (password_hash/is_active)")
    except Exception as e:
        print(f"⚠️ Feed user auth columns migrate failed: {e}")

    # 旧桌宠设置死列清理：feed_users.pet_settings 已废弃（改为按 AI 同事角色统一形象）
    try:
        drop_pet_settings_column()
        print("✅ Feed user pet_settings dead column dropped")
    except Exception as e:
        print(f"⚠️ Feed user pet_settings dead column drop failed: {e}")

    # 评论节点归属：opportunity_messages 加 node_key（审批节点内评论线程）
    try:
        ensure_feed_message_node_key()
        print("✅ Feed message node_key column ensured")
    except Exception as e:
        print(f"⚠️ Feed message node_key migrate failed: {e}")

    # 商机归属：opportunities.opportunities 加 owner_user_id（个人商机/全量视图过滤依据）
    try:
        ensure_opportunity_owner_column()
        print("✅ Opportunity owner column ensured (owner_user_id)")
    except Exception as e:
        print(f"⚠️ Opportunity owner column migrate failed: {e}")
    # 报价单发送状态：submitted_at/submitted_by/submitted_attachment_id + 旧 done 数据回退
    try:
        ensure_quotation_submission_columns()
        print("✅ Quotation submission columns ensured (submitted_at/submitted_by/submitted_attachment_id)")
    except Exception as e:
        print(f"⚠️ Quotation submission columns migrate failed: {e}")
    try:
        backfill_premature_done_flows()
        print("✅ Premature done flows backfilled to running")
    except Exception as e:
        print(f"⚠️ Premature done flows backfill failed: {e}")
    try:
        ensure_quotation_config_relation_columns()
        print("✅ Quotation config_relation/primary_config columns ensured")
    except Exception as e:
        print(f"⚠️ Quotation config_relation migrate failed: {e}")
    try:
        ensure_bom_scheme_config_relation_columns()
        print("✅ BOM scheme config_relation/primary_config columns ensured")
    except Exception as e:
        print(f"⚠️ BOM scheme config_relation migrate failed: {e}")
    # 反向回填已改为显式迁移脚本，不再随启动自动执行。
    # 见 backend/scripts/migrate_legacy_flow_artifacts.py。
    try:
        repair_bom_scheme_l6_rows()
        print("✅ Legacy BOM/cost L6 rows repaired")
    except Exception as e:
        print(f"⚠️ BOM/cost L6 row repair failed: {e}")
    try:
        ensure_bootstrap_admin()
    except Exception as e:
        print(f"⚠️ Bootstrap admin init failed: {e}")

    # RBAC：权限目录 + 角色种子（幂等，仅首次）
    try:
        ensure_permission_catalog()
    except Exception as e:
        print(f"⚠️ Permission catalog init failed: {e}")
    try:
        ensure_roles_table_and_seed()
    except Exception as e:
        print(f"⚠️ Roles seed failed: {e}")

    # Clean up old temporary files on startup
    try:
        from app.utils.file_storage import FileStorage
        fs = FileStorage()
        removed = fs.cleanup_temp(max_age_hours=24)
        if removed:
            print(f"🧹 Cleaned up {removed} old temp file(s)")
    except Exception:
        pass

    # AI Office runtime event / resolved governance retention
    try:
        from app.repository.office_event_repo import OfficeEventRepository
        from app.repository.office_governance_repo import OfficeGovernanceRepository
        event_removed = OfficeEventRepository().prune_runtime_events()
        gov_removed = OfficeGovernanceRepository().prune_resolved()
        if event_removed or gov_removed:
            print(f"🧹 AI Office retention: {event_removed} runtime events, {gov_removed} resolved governance items")
    except Exception:
        pass
