---
name: bp-type-migrated-to-cre
description: 背板类型判定 bp_type 从 DerivationEngine 死代码迁到 CRE derive 赋值规则（2026-07-30），选型配置页可配改即生效；碰背板/CRE derive 前先看
metadata: 
  node_type: memory
  type: project
  originSessionId: 3bf6f12d-6ff4-4f06-8921-1ed4cc44342d
  modified: 2026-07-30T10:14:41.790Z
---

**⚠️ 2026-07-30 后续：DerivationEngine 整体已删**，线缆/GPU线也随本次迁入 CRE derive 驱动（见 [[strategy-center]] 顶部定调）。本文件下方关于 DerivationEngine/DERIVATIONS/DeriveResult/derive_front_cables 的细节仅供历史参考，**现状以 [[strategy-center]] 顶部 2026-07-30 定调为准**（CRE 6 条 seed、线缆 target=类型标签、L6ChassisConfig 注入 derivedCableQty）。bp_type 赋值机制本身不变（仍 CRE derive 赋值 + evalAssignValue 首命中 + 消费端 ?? 'dc' 兜底）。

2026-07-30：背板类型判定（bp_type：含 NVMe 盘→tri 三模；纯 SATA/SAS 或无盘→dc 直通）从后端 `DerivationEngine.derive_bp_type` 迁到 **CRE 兼容性规则**（derive 类型），选型配置页 derive tab 声明式编辑、改即生效。用户定调：分支判定型规则要可配置生效，不接受「描述文字能改、行为不变」的假透明（第一版做 name/logic 文字编辑被否决）；公式计算型（功耗/PSU/线缆/GPU线/Switch）仍留 DerivationEngine + 参数可调（参数改了已真生效）。

- **赋值型 derive**：CRE 的 derive 动作原为纯算术（`basis÷per→数量`），新增赋值型 `then:{action:'derive', field, value}`（条件→固定值）。`selectionEngine.ts` 的 evalThen 按 then 形态分派；新增 `evalAssignValue(rules,ctx,field)` 按规则顺序**首命中**（具体规则放前、宽泛放后；dc 兜底由消费端 `bpType() ?? 'dc'`，不 seed dc 规则——CRE 无 not-contains）。单测 32 例（node --test）。
- **种子**：`compatibility_rule_repo.DEFAULT_RULES` ⑤ derive「含 NVMe 盘→三模」(when `config.drive_kinds contains NVMe` → then `config.bp_type=tri`)。硬件语义：tri-mode 背板支持 SATA/SAS/NVMe 三协议、dc 直连只走 SATA/SAS，故有 NVMe 盘必须 tri（旧种子「含机械盘→tri」判定写反，已于 2026-07-30 纠正）。⚠️ **线上库已有数据不会自动 seed ⑤**，需 `POST /api/compatibility-rules/reset`（清自定义规则）或手动建等效规则（线上 id=5 已手改为 NVMe→tri）。
- **求值落点**：`L6ChassisConfig` 用 `kpSummary.drivesByKind` 算 `drive_kinds` → `selectionRulesStore.assignValue('config.bp_type', ctx)` → 注入 `useServerConfig.derivedBpType`；`bpType()` 优先级 `手改 > 基准自带 > CRE 规则 > dc`。改规则 → `invalidateRules` → computed 重算 → 背板料号自动换（改即生效闭环）。
- **清理**：`derive_bp_type` 删、`derive_all` 去 bp_type 字段、`DERIVATIONS` 去 bp_type 条目（DerivationRulesPanel 不再显示）、`DeriveResult` 去 bp_type；`_drive_kinds` 保留（`derive_front_cables` 仍用）。`CompatibilityRuleEditor` derive 分支加「赋值/算术」子模式 + `whenText` 修 `any` 支持（原只认 all/单条件）。

关联：[[strategy-center]] CRE 全景、[[derive-must-have-manual-fallback]] 推导仅兜底（bpType 手改仍优先于规则）、[[reasoning-flow-viz]]。
