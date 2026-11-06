-- 2026-11-06 平台系列代号去内部化：Polaris → 兆芯、Orion → AMD（用户拍板批量统一为芯片品牌口径）。
-- 背景：platform_type/系列/规则/料号 compat 全链路存内部代号，驾驶舱按品牌归桶恒为 0（AMD/Orion、兆芯/Polaris 映射错位）。
-- 权威映射（public_intake 同源）：AMD=Orion 系列，兆芯=Polaris 系列；'INTEL&Orion' 历史脏值一并跟随 → 'INTEL&AMD'。
-- 范围：结构化业务数据与规则。明确不改：
--   * 自然语言历史（requirement_text / assistant_messages.content / opportunity_messages.body / colleague_memories.content）
--   * 审计 rules.agent_audit_log
--   * 磁盘文件引用 opportunities.*.file_path / opportunity_attachments.storage_key（真实文件名未动）
--   * _bak/_old 备份表
-- 幂等：replace 天然幂等，可重复执行。执行前先备份目标表（2026-11-06 本地/服务器均归档于 CPQ_Archive）。

-- ── 商机域 ──
UPDATE opportunities.opportunity_requirements SET slots = replace(replace(slots::text,'Polaris','兆芯'),'Orion','AMD')::json WHERE slots::text ~ '(Polaris|Orion)';
UPDATE opportunities.opportunities SET extra_fields = replace(replace(extra_fields,'Polaris','兆芯'),'Orion','AMD') WHERE extra_fields ~ '(Polaris|Orion)';
UPDATE opportunities.opportunity_bom_schemes SET configs = replace(replace(configs::text,'Polaris','兆芯'),'Orion','AMD')::json WHERE configs::text ~ '(Polaris|Orion)';
UPDATE opportunities.opportunity_cost_sheets SET configs = replace(replace(configs::text,'Polaris','兆芯'),'Orion','AMD')::json WHERE configs::text ~ '(Polaris|Orion)';
UPDATE opportunities.quotations SET
  strategy_snapshot = replace(replace(strategy_snapshot::text,'Polaris','兆芯'),'Orion','AMD')::json,
  cost_snapshot    = replace(replace(cost_snapshot::text,'Polaris','兆芯'),'Orion','AMD')::json,
  extra_fields     = replace(replace(extra_fields,'Polaris','兆芯'),'Orion','AMD')
  WHERE strategy_snapshot::text ~ '(Polaris|Orion)' OR cost_snapshot::text ~ '(Polaris|Orion)' OR extra_fields ~ '(Polaris|Orion)';
UPDATE opportunities.quotations SET config_server_models = replace(replace(config_server_models::text,'Polaris','兆芯'),'Orion','AMD')::json WHERE config_server_models::text ~ '(Polaris|Orion)';
-- 在途会话结构化状态（content 自然语言不动）
UPDATE opportunities.assistant_messages SET data = replace(replace(data,'Polaris','兆芯'),'Orion','AMD') WHERE data ~ '(Polaris|Orion)';
UPDATE opportunities.assistant_threads SET reasoning_state = replace(replace(reasoning_state,'Polaris','兆芯'),'Orion','AMD') WHERE reasoning_state ~ '(Polaris|Orion)';

-- ── 规则域（改完即生效）──
UPDATE rules.strategies SET
  name = replace(replace(name,'Polaris','兆芯'),'Orion','AMD'),
  scope = replace(replace(coalesce(scope,''),'Polaris','兆芯'),'Orion','AMD'),
  description = replace(replace(coalesce(description,''),'Polaris','兆芯'),'Orion','AMD'),
  body = replace(replace(coalesce(body,''),'Polaris','兆芯'),'Orion','AMD')
  WHERE name ~ '(Polaris|Orion)' OR coalesce(scope,'') ~ '(Polaris|Orion)' OR coalesce(description,'') ~ '(Polaris|Orion)' OR coalesce(body,'') ~ '(Polaris|Orion)';
UPDATE rules.compatibility_rules SET
  name = replace(replace(name,'Polaris','兆芯'),'Orion','AMD'),
  body = replace(replace(body,'Polaris','兆芯'),'Orion','AMD')
  WHERE name ~ '(Polaris|Orion)' OR body ~ '(Polaris|Orion)';
UPDATE rules.matching_rules SET description = replace(replace(description,'Polaris','兆芯'),'Orion','AMD') WHERE description ~ '(Polaris|Orion)';
UPDATE rules.system_config SET value = replace(replace(value,'Polaris','兆芯'),'Orion','AMD') WHERE value ~ '(Polaris|Orion)';
UPDATE rules.reasoning_node_config SET config = replace(replace(config,'Polaris','兆芯'),'Orion','AMD') WHERE config ~ '(Polaris|Orion)';
UPDATE rules.bom_cases SET
  scenario_tags = replace(replace(scenario_tags::text,'Polaris','兆芯'),'Orion','AMD')::jsonb,
  notes = replace(replace(coalesce(notes,''),'Polaris','兆芯'),'Orion','AMD')
  WHERE scenario_tags::text ~ '(Polaris|Orion)' OR coalesce(notes,'') ~ '(Polaris|Orion)';
UPDATE rules.office_governance_items SET payload = replace(replace(payload::text,'Polaris','兆芯'),'Orion','AMD')::jsonb WHERE payload::text ~ '(Polaris|Orion)';

-- ── 服务器/料号/KP 域 ──
-- base_config_parts.pn → parts_master.pn 外键父/子都要改,需把约束临时改 DEFERRABLE,事务提交时统一校验
DO $$ DECLARE c text; BEGIN
  SELECT conname INTO c FROM pg_constraint
    WHERE conrelid = 'l6.base_config_parts'::regclass AND confrelid = 'l6.parts_master'::regclass AND contype = 'f'
    ORDER BY conname LIMIT 1;
  IF c IS NOT NULL THEN
    EXECUTE format('ALTER TABLE l6.base_config_parts ALTER CONSTRAINT %I DEFERRABLE INITIALLY IMMEDIATE', c);
    EXECUTE format('SET CONSTRAINTS l6.%I DEFERRED', c);
  END IF;
END $$;
UPDATE l6.base_configs SET
  series = replace(replace(series,'Polaris','兆芯'),'Orion','AMD'),
  config_content = replace(replace(config_content::text,'Polaris','兆芯'),'Orion','AMD')::jsonb
  WHERE series ~ '(Polaris|Orion)' OR config_content::text ~ '(Polaris|Orion)';
UPDATE l6.parts_master SET
  pn = replace(replace(pn,'Polaris','兆芯'),'Orion','AMD'),
  name = replace(replace(name,'Polaris','兆芯'),'Orion','AMD'),
  description = replace(replace(coalesce(description,''),'Polaris','兆芯'),'Orion','AMD'),
  spec_text = replace(replace(coalesce(spec_text,''),'Polaris','兆芯'),'Orion','AMD'),
  specs = replace(replace(specs::text,'Polaris','兆芯'),'Orion','AMD')::jsonb
  WHERE pn ~ '(Polaris|Orion)' OR name ~ '(Polaris|Orion)' OR coalesce(description,'') ~ '(Polaris|Orion)' OR coalesce(spec_text,'') ~ '(Polaris|Orion)' OR specs::text ~ '(Polaris|Orion)';
UPDATE l6.base_config_parts SET pn = replace(replace(pn,'Polaris','兆芯'),'Orion','AMD') WHERE pn ~ '(Polaris|Orion)';
UPDATE l6.server_models SET product_content = replace(replace(product_content::text,'Polaris','兆芯'),'Orion','AMD')::jsonb WHERE product_content::text ~ '(Polaris|Orion)';
UPDATE l6.l6_rear_panel_items SET applicable_chassis = replace(replace(applicable_chassis,'Polaris','兆芯'),'Orion','AMD') WHERE applicable_chassis ~ '(Polaris|Orion)';
DO $$ DECLARE c text; BEGIN
  SELECT conname INTO c FROM pg_constraint
    WHERE conrelid = 'l6.base_config_parts'::regclass AND confrelid = 'l6.parts_master'::regclass AND contype = 'f'
    ORDER BY conname LIMIT 1;
  IF c IS NOT NULL THEN
    EXECUTE format('SET CONSTRAINTS l6.%I IMMEDIATE', c);
    EXECUTE format('ALTER TABLE l6.base_config_parts ALTER CONSTRAINT %I NOT DEFERRABLE', c);
  END IF;
END $$;
UPDATE kp.kp_parts SET applicable = replace(replace(applicable::text,'Polaris','兆芯'),'Orion','AMD')::jsonb WHERE applicable::text ~ '(Polaris|Orion)';
UPDATE kp.kp_part_search_index SET applicable = replace(replace(applicable::text,'Polaris','兆芯'),'Orion','AMD')::json WHERE applicable::text ~ '(Polaris|Orion)';

-- ── ai_read 为视图层,自动跟随源表,无需迁移 ──


