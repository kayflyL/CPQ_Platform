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
from app.models.requirement_rule import RequirementRule, RequirementSample  # 需求分析规则库
from app.models.llm_trace import LLMTrace  # LLM 调用审计 trace（P3 指标）（注册 metadata 供 create_all 建表）
from app.models.compatibility_rule import CompatibilityRule  # 兼容性规则引擎（注册 metadata 供 create_all 建表）
from app.models.policy_doc import PolicyDoc  # 策略文档库独立表（注册 metadata 供 create_all 建表）
from app.repository.rules_repo import RulesRepository
from app.repository.system_config_repo import SystemConfigRepository
import json


def ensure_policy_docs_table_and_migrate():
    """策略文档库独立表 rules.policy_docs（幂等自愈，boot 时执行）：

    1) 建表 + 唯一索引 (module, created_at) —— 时间戳定位的稳定性保证；
    2) 一次性把 rules.strategies 里旧文档（domain=policy, type=document）搬进新表
       （保留 created_at/updated_at/version/创建人），搬完从 strategies 删除——
       文档不再与定价/选型规则混表，不再有自增数字 id，增删改查用「创建时间戳」定位。
    """
    from sqlalchemy import text
    from app.models.base import rules_engine
    with rules_engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS rules.policy_docs (
                doc_key varchar(36) PRIMARY KEY,
                module varchar NOT NULL,
                name varchar NOT NULL,
                category varchar NOT NULL DEFAULT '总览',
                sort_order integer NOT NULL DEFAULT 1,
                content_markdown text NOT NULL DEFAULT '',
                description text,
                status varchar NOT NULL DEFAULT 'active',
                version integer NOT NULL DEFAULT 1,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                created_by varchar NOT NULL DEFAULT 'system',
                updated_by varchar NOT NULL DEFAULT 'system'
            )
        """))
        c.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_policy_docs_module_created "
            "ON rules.policy_docs(module, created_at)"
        ))
        c.execute(text("CREATE INDEX IF NOT EXISTS idx_policy_docs_module ON rules.policy_docs(module)"))
        # 一次性迁移旧 strategies 文档（幂等：ON CONFLICT 跳过已搬的；搬完删 strategies 文档行）
        c.execute(text("""
            INSERT INTO rules.policy_docs
                (doc_key, module, name, category, sort_order, content_markdown,
                 description, status, version, created_at, updated_at, created_by, updated_by)
            SELECT
                md5(name || '|' || COALESCE(created_at::text, ''))::varchar(36),
                COALESCE(body::jsonb->>'module', 'pricing'),
                name,
                COALESCE(NULLIF(body::jsonb->>'category', ''), '总览'),
                COALESCE((body::jsonb->>'sort_order')::int, 1),
                COALESCE(body::jsonb->>'content_markdown', ''),
                description, status, version,
                created_at::timestamptz, updated_at::timestamptz, created_by, updated_by
            FROM rules.strategies
            WHERE domain='policy' AND type='document'
            ON CONFLICT (module, created_at) DO NOTHING
        """))
        c.execute(text("DELETE FROM rules.strategies WHERE domain='policy' AND type='document'"))


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


def init_rules_db():
    """Create rules database tables and initialize default rules if empty."""
    # Create all tables for rules DB
    Base.metadata.create_all(bind=rules_engine)
    # Create tables for L6 history DB
    Base.metadata.create_all(bind=l6_history_engine)
    # Create tables for opportunities DB (includes spec_templates)
    Base.metadata.create_all(bind=opp_engine)
    
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

    # Initialize system_config defaults
    config_repo = SystemConfigRepository()
    try:
        config_repo.init_defaults()
        print("✅ System config initialized")
    finally:
        config_repo.close()

    # Reasoning flow default seed + v2 migrate（加 clarity_check/ask_user/budget_check）
    try:
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        rf_repo = ReasoningFlowRepository()
        try:
            rf_repo.seed_default_if_empty()
            migrated = rf_repo.migrate_v1_to_v2_if_needed()
            if migrated:
                print("✅ Reasoning flow migrated to v2 (clarity_check/ask_user/budget_check)")
            else:
                print("✅ Reasoning flow initialized")
            if rf_repo.fix_cond_clarity_threshold():
                print("✅ cond_clarity 阈值自愈：unclear-only → 非 explicit 都反问（修模糊需求不反问 bug）")
            if rf_repo.migrate_extract_model_token_regex():
                print("✅ extract model_token_regex 自愈：恢复 H100/A100 单字母+3位数字分支")
            if rf_repo.migrate_ask_user_to_catalog():
                print("✅ ask_user 配置自愈：rebuttal/workload 话术 → 目录驱动引导（类型→机型→KP 格式）")
            if rf_repo.migrate_v3_scene_analysis_if_needed():
                print("✅ Reasoning flow migrated to v4 (scene_analysis/cond_scene)")
            if rf_repo.migrate_v5_normalize_input_if_needed():
                print("✅ Reasoning flow migrated to v5 (normalize_input)")
            if rf_repo.migrate_v6_llm_understand_if_needed():
                print("✅ Reasoning flow migrated to v6 (llm_understand/slot_validate)")
            if rf_repo.migrate_v7_confirm_if_needed():
                print("✅ Reasoning flow migrated to v7 (confirm 确认面板)")
            if rf_repo.migrate_v8_llm_audit_if_needed():
                print("✅ Reasoning flow migrated to v8 (llm_audit 方案校对)")
        finally:
            rf_repo.close()
    except Exception as e:
        print(f"⚠️ Reasoning flow init failed: {e}")

    # Requirement rules default seed (需求分析规则库：clarity/budget)
    try:
        from app.repository.requirement_rule_repo import RequirementRuleRepository
        rr_repo = RequirementRuleRepository()
        try:
            n = rr_repo.seed_default_if_empty()
            if n:
                print(f"✅ Requirement rules initialized ({n} rules)")
            else:
                print("✅ Requirement rules already present")
            # 按名非破坏补种新增默认项（新 clarity/rebuttal 规则随迭代自动补上，不动用户已有改动）
            m = rr_repo.seed_missing_defaults()
            if m:
                print(f"   + {m} new requirement rule(s) appended (non-destructive)")
            # 目录驱动引导上线：删除已废弃的 rebuttal/workload 旧规则与样本（幂等）
            d = rr_repo.cleanup_obsolete_rules()
            if d:
                print(f"   🧹 removed {d} obsolete requirement rule(s) (rebuttal/workload)")
        finally:
            rr_repo.close()
    except Exception as e:
        print(f"⚠️ Requirement rules init failed: {e}")

    # 兼容规则分类列 DDL（必须在 ORM seed/backfill 前跑，确保列存在）
    try:
        ensure_compatibility_rule_category()
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

    # 策略文档库：独立表 rules.policy_docs（无数字 id，增删改查用创建时间戳定位）。
    # 无任何硬编码种子（曾用 DEFAULT_DOCS 补种导致"前端删除的文档被重启复活"，已彻底移除）。
    try:
        ensure_policy_docs_table_and_migrate()
        print("✅ Policy docs table ensured (no id, timestamp-keyed)")
    except Exception as e:
        print(f"⚠️ Policy docs table init failed: {e}")

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

    # Clean up old temporary files on startup
    try:
        from app.utils.file_storage import FileStorage
        fs = FileStorage()
        removed = fs.cleanup_temp(max_age_hours=24)
        if removed:
            print(f"🧹 Cleaned up {removed} old temp file(s)")
    except Exception:
        pass
