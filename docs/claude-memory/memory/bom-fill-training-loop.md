---
name: bom-fill-training-loop
description: 需求分析→BOM 训练循环（真实样本对照技术员 BOM）产出的引擎修改与待办。⚠️2026-08-07 起 extract 冻结，新差异走 llm_agent prompt（见 [[agent-understand-hybrid]]），不再加 regex。doc 实际在 docs/策略中心/04-共享层/训练经验总结与学习闭环.md
metadata: 
  node_type: memory
  type: project
  originSessionId: 4d154b82-9bd9-4419-b4a8-49bb8f52e5a9
  modified: 2026-08-07T04:29:50.150Z
---

2026-08-02 起，用户用「需求文本 → 系统推理 BOM」对照「技术员真实 BOM」的方式训练系统如何填机箱配件层。**训练记录与规则草案全在 [docs/training/bom-fill-learnings.md](../../../../D:/CPQ_Platform_V1/docs/training/bom-fill-learnings.md)**（每轮 diff + R-1..R-11 规则表），碰 rear-IO/BOM 填充/推理节点前先看。

**已落地的引擎修改（训练驱动，证据见对应轮次）：**
- **R-1 OCP 不自动填**：`candidate_search.py::_rear_slot_option` 的 OCP 分支已关（return None）。2 轮真实样本（4U 千兆 + 4U 25G）证实网络一律走 PCIe 网卡（I350/CX4，KP 件），从不占 OCP。推翻了原"OCP 是标准网卡位必填"的行业假设。
- **R-9 非 AI 需求 abort 修复**：`requirement_intel_service.py` extract 兜底——识别到服务器品类(CPU/内存/盘/RAID/网卡)却无用途词时 usage='通用计算'（排除 GPU 类）。此前规格清单式需求（无"AI/存储/通用"词）usage=None→select_models 0 机型中止，**所有非 AI 的通用/存储服务器需求全部失败**。修后命中 2U 通用机型。
- **R-13 PSU 显示（已纠正层位，[0.1.35]）**：[0.1.34] 的 `fill_psu`（往 bom_excel_rows 塞电源行）**层位错了**——bom_excel_rows 是无模板时的 excel 兜底，模板模式 BomTable 不读它。现改为：`build_plan` 按 GPU 数推断瓦数注入 `plan.chassis_signals.psu_wattage`（需求文本功率优先），前端模板 PSU 行(`${psu_wattage}W`×psu_qty)据此渲染；`usePlanBom.deriveVars` 的 `psu_qty` 改取 `base.psu_bays`。`fill_psu`/`fill_rear_io`/`_rear_slot_option` 已删。
- **R-14 风扇件补库**：parts_master 原无风扇件，加占位件 `S.E.M.0000501`「系统风扇(2U)」并挂全部 2U base_config ×6（价 0 待补，见 docs/待确认事项.md）。层位正确（parts 喂模板风扇行）。4U 风扇情况不明（技术员 4U BOM 未列风扇，可能 bundled），暂不补。
- **R-16 PSU 瓦数按 GPU 功耗分档**（[0.1.36]）：8×低功耗 GPU(R9700) 之前被估 2700W，实际 2000W。`_kp_signals` 加 `high_tdp` 识别（H100/A100/H200/B200/L40/MI300/RTX PRO/RTX 6000/RTX 5090），`_infer_psu_wattage(gpu_qty, high_tdp)`：≥8 且高功耗→2700，其余有 GPU→2000，无→1600。
- **R-6 数量串台 + R-8 过匹配**（[0.1.37]，任务#40 完成）：R-6 改「位置绑定+方向感知」qty 解析（后缀式绑前品类/前缀式绑后品类，乘号负向回望防×8条重复匹配），不再「块→CPU」固定映射；R-8 stage-1 跳过纯容量碎片(480G/3.84T) + Memory 有 mem_signal 时跳过交 stage-2 反推。验证 round5 CPU×2/内存 64G×8/GPU×8/SSD×2 全对（此前 SSD 盗内存16、NIC 串成8、内存 32G×2）。

**BOM 显示架构（重要，[0.1.35] 厘清）**：显示层 = **前端 BOM 模板**（`usePlanBom.buildPlanCfg` 取 baseline 的 bom_template.rows + base_config.parts + 派生 vars + chassis_signals → `bomRuleEngine.evalBomContext` 求值 → BomTable live 渲染）。`plan.cfg.bom_excel_rows` 只是**无模板时 excel 兜底**。**10 个 base_config 全已选 bom_template_id**（2U→tpl1、4U直连→tpl2、4U Switch→tpl3），模板齐全且与技术员 BOM 行数对得上（2U 含风扇行、4U 无 riser）。`deriveVars` 关键修复：gpu_qty/drive_count 从 KP items 算（原从机箱件算是 0）、psu_qty 取 psu_bays、gpu_cable_qty=gpu_qty。仍空：rear/frontCables（推理没选 rear，io_slot/后背板汇总行空，交工作台选配器）。

**待数据/实现（docs/待确认事项.md）**：①Cable 随 RAID 卡+盘类型变（R-17，模板有 frontCableQty 机制但推理喂 0，需线缆 PN+数量规则）；②KP 料库缺口(100G MCX5/R9700/P5510)；③内存速率分档(9004→4800/9005→6400，系统偶尔选错如 9654 选 6400)；④风扇价(占位0)。

**4U BOM 明细架构（重要，澄清 pain④）**：4U 背板/散热器/电源/线缆明细**不在 base_config.parts（那是 1 个 lump），而在 `bom_templates`（4U8-GPU直连 id=2 / 4U8-Switch id=3）的 rows 规则**里——按 `psu_qty/psu_wattage/gpu_cable_qty/part_quantity/struct_count` 算出，正好对应技术员 8 行，且**无 riser 行**（4U 没 riser，用户确认）。工作台走模板（BOM 全），**推理 build_plan 不走模板**（只搬 base_config.parts+fill_rear_io+fill_psu）→ 智能生成 BOM 入口的 4U 底盘偏粗。是否让推理也套模板待用户定（docs/待确认事项.md #4）。

**待办（未修，记在 learnings + 任务 #37/#38/#40）：**
- **R-6/R-8（任务 #40）**：KP 数量解析只认后缀 `*N` 不认前缀「N块型号」（SSD 盗内存 16、GPU 漏成 1）；stage-1 关键词匹配无品类去重（1 数据盘返回 4 候选）。根因已定位，待积累样本后统一重构。
- **R-10（任务 #37 pain④，已收窄）**：BOM 原不出现 PSU/FAN/Riser——现 PSU 已走推理填充(R-13)、2U 风扇已补库挂载(R-14)。**剩余**：①Riser——库里 ×8 单槽(0002346/0002539)与技员三槽 IO1/IO2(1×X16+2×X8)对不上，且技员 BOM 无"riser"一词，按用户意见搁置；②4U 风扇——技术员 4U BOM 未列风扇，是否 bundled 待定；③4U base_config 仍是 1 个 lump（无背板/散热器/线缆明细），pain④ 主战场待补真实 PN。
- **R-12（KP 库缺口）**：NVIDIA H100 80G 不在 kp_parts 库→推理兜底成 W7900 错配。需补 H100 料号。
- **用户否决的设计**：不要加"无 GPU→默认 2U"form 推断——无 GPU 也可能是 4U(客户自购 GPU)。form 保持显式或触发澄清反问。
- **R-18 / 设计纠正（不要给 4U base_config 补件填空）**：前端实测 4U「智能生成 BOM」L6 多行空，我曾诊断成"4U 只有 lump 1 件→模板 part_field 行找不到件"并补了散热器/导轨/GPU电源线，**用户撤回**。真相：①**4U base_config = 整机箱 lump 是有意的**（4U 机箱还没拆件，lump 代表整机箱价，L6 偏空/偏粗是预期，等 pain④ 拆解）；②**GPU电源线不是机箱件**——是报价工作台按 GPU 数人工加的配件(跟 PSU 类似按需配)，不该塞 base_config。**下次别再往 4U base_config 补件去"填空"。** 见 CHANGELOG 0.1.38 + learnings R-18。
- **R-5（任务 #38）**：推理不区分 Switch/直连变体（后背板 3×X16 vs 3×X8）。
- **R-11**：rear_slots 是容量上限非必装（2U 只装 IO1+IO2，IO3/IO4/OCP 留空），印证不该被 fill_rear_io 全填。

关联：[[l6-baseconfig-capability-state]]（OCP 填充校正已并入此记忆）、[[reasoning-match-enhanced]]、[[strategy-center]]。
