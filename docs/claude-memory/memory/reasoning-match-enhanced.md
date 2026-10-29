---
name: reasoning-match-enhanced
description: 推理流匹配四块增强(2026-07-31)：内存容量反推条数+CPU双路、同品类多规格网卡、底盘件信号注入、机型不硬塞GPU；碰推理流匹配/选型前先看
metadata: 
  node_type: memory
  type: project
  originSessionId: 3943c602-5ec3-4231-a75f-89b3a9f41203
  modified: 2026-07-31T09:53:37.825Z
---

2026-07-31 商机详情页推理流（[[opportunity-detail-intel]]）匹配逻辑四块增强，解决「自然语言需求→推荐配置」大面积偏离（实测一条需求 9 项 8 错：CPU×1 应 ×2、内存 16G DDR4 应 32G DDR5×8、网卡 1 张应 2 张、GPU 硬塞应无、电源/Heatsink/Cable 空）。改的都是 `pick_kp_parts`/`extract_keywords`/`select_models`，两条执行路径（图 `reasoning_executor._dispatch` + 线性 `_run_linear_fallback`）共用这批函数，改一处两路受益。验证用 `backend/scripts/simulate_requirement.py "需求文本"`。

**A 内存/CPU**（`candidate_search._pick_memory_part` + `_memory_kp_row`；`requirement_intel_service._extract_mem_signal/_extract_cpu_signal`）：mem_signal{total_gb,type,speed}——按段切只取含 DDR/D5/内存 的段提 G 值，避免误抓「480G启动盘」；pick Memory 分支按 Type+Speed spec 过滤 + 容量反推（选使条数接近 8 双路通道的整除容量，256G→8×32G 而非 4×64G）；cpu_signal.duality（全套/双路/满配/2颗）→ qty_map[CPU]=2。末尾 qty 注入段加 `if kp.get('qty')` 保留反推值不被覆盖。

**B 同品类多规格**（`pick_kp_parts` multi_spec_filters）：`spec_aliases` 加 spec_filter（千兆→Link Speed=1G、万兆→10G），extract 收集成 `multi_spec_filters{cat:[sf]}`，pick stage1 跳过 multi_spec 品类、stage2 按每个 sf 各产出一件（千兆+万兆两张网卡）。`_is_multi` 放行品类级 continue + 全 sf 未命中（spec 稀疏）落回通用兜底（`_produced` 检查）。

**C 底盘件**（前端 `usePlanBom`/`bomRuleEngine`）：`findPart` 加中英对照表（heatsink↔散热器、rail↔滑轨、cable↔线缆——修 Heatsink 空值根因：模板填英文 category、底盘件 category 中文）；`deriveVars` 加 psu_wattage(从 plan.chassis_signals)/bp_type/form/series；`buildPlanCfg` 注入背板件（bp_tri_pn→parts，对齐工作台 effectiveBaseParts）。后端 `_extract_psu_signal`(电源配1300→1300) + 两处 compose 段塞 `plan.chassis_signals`。**边界**：PSU 显示功率/背板 NVMe 文案/IO·Cable 真值依赖 DB `bom_templates` row kind（代码已铺 vars/parts，需管理员把模板 row 改 config_value/part_field + 对应 vars 才生效）；IO1/IO2、Cable 是选配交互产物（rear/frontCable），推理阶段填不出真值，标「待选配」（符合 [[derive-must-have-manual-fallback]]）。

**D 机型不硬塞 GPU**（`select_models`/`_match_type_by_usage` + `kp_categories_for_type`）：usage 空但有 form → 兜底「通用计算」type_id（不混 AI/存储）；`kp_categories_for_type` 加 requested_cats，GPU 仅需求含 GPU 才配（AI 套餐不再硬塞，None 时向后兼容不过滤）；`list_models` `ORDER BY sort_order, m.id`；修 `simulate_requirement.py` models[0] bug → per-机型套餐对齐线上。**注**：线上 `reasoning_executor` 本就 per-机型套餐（通用机型不配 GPU），simulate 的 models[0] bug 曾放大此问题误导诊断。

**前置**（[[kp-spec-coverage-sparse]]）：`get_by_category_with_spec_filter`（`kp_repo`）重写——原单条件+数值+`^[0-9]`guard（Type=DDR5 字母被跳过），改为 ORM 全取+Python AND（`_spec_match_all`：多条件、等值/IN、数值范围分流）。matched_spec 标签显示真实 spec_value（DDR5/1G/32 GB）。Memory 的 Capacity/Type/Speed、NIC 的 Link Speed 全覆盖。

**⚠️ 线上 DB 同步**：`_default_node_configs` 改了 spec_aliases（加 spec_filter）。线上 reasoning_flow node_configs 仍旧版，需重 seed/reset（节点 config 编辑器或 API）才生效；simulate 直接读种子立即生效。关联 [[strategy-center]]、[[reasoning-flow-viz]]。
