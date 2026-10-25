---
name: l6-baseconfig-capability-state
description: 真实配置归纳的 L6 底座图谱 + base_config 能力档案已回填 + seed 误导 + 待办决策
metadata: 
  node_type: memory
  type: project
  originSessionId: 4d154b82-9bd9-4419-b4a8-49bb8f52e5a9
  modified: 2026-10-22T02:36:34.457Z
---

基于 15 份真实项目配置表(2U×7 + 4U×8,2026-08「配置代表」)归纳出 **5 类底座**:AMD-2U 通用(ES22V3-P)、海光-2U 通用(ZS22V2-P,KH-50000)、AMD-4U Switch(ESA24V3-P,8 GPU 槽)、AMD-4U 直连(ESA24V3-P,同机型双变体)、海光-4U Switch(ZSA24V2-P,PCIe5.0)。关键校正:PCIe 不是干净「三档」而是平台×机箱×档位矩阵;OCP 是 AMD 平台特性(海光 2U 无、海光 4U 有);电源瓦数随 GPU 功耗;海光 KH-50000 是第三平台。

**seed_demo_data.py 误导**:它只建 4 条 2U base_config,但真实 DB 早有更全配置(管理面建的):ESA24V3-P 直通(id=23)+Switch(id=25)双变体挂 model 16、ZSA24V2-P(id=22)、4.5U 变体等,共 10 条。**碰 base_config 别看 seed,直查 DB**(`scripts/backfill_chassis_capability.py` 末尾审计查询)。

**能力档案已回填**(backfill_chassis_capability.py,保守幂等):原全是 migrate 默认值(psu=2/gpu=0/tdp=None/2U 布局),现按 form×series 校正——2U psu=2/gpu=0、4U psu=4/gpu=8、max_tdp Orion=1000(500W×2)/Polaris=900(450W×2)、2U 海光 rear 去 OCP、**4U rear=仅OCP**(2026-08-02 纠正:IO1-4 是 2U 通用机概念,4U GPU 机业内不用 GPU 槽与 IO 槽分区,见 Dell XE9680/HPE DL380 GPU cage;GPU 走 gpu_slots+gpu_arch)。rear_slots 模板在 `chassisMeta.ts`(REAR_SLOTS_2U_AMD/2U_HAIGUANG/4U=[OCP] + rearSlotsFor)。

**后面板填充引擎 fill_rear_io 训练校正**(2026-08-02,候选搜索 candidate_search.py,训练记录 docs/training/bom-fill-learnings.md):2 轮真实样本(4U 千兆 + 4U 25G)**均不填 OCP**——网络一律走 PCIe 网卡(I350/CX4,KP 件),与网速无关。故 `_rear_slot_option` 的 OCP 分支已**关闭(return None)**,推翻原"OCP 是标准网卡位必填"。当前 fill_rear_io 只在「有 GPU」时填 IO1/IO2=X16 Riser,OCP/IO3/IO4 一律留空交手填。4U chassisMeta 的 rear_slots=[OCP] **暂保留为可选空槽**(槽存在≠自动填)。bom_templates 底盘件明细(背板/散热器/电源/线缆)仍欠,属 pain④。

**CRE 边界**(重要):机箱能力字段(psu_bays/gpu_slots/rear_slots)不在 CRE 求值 ctx(只有 kp.*/config.*/opportunity.*),所以电源↔GPU 功率、PCIe 档位、盘位、后面板规律**做不成 CRE 规则**,靠 base_config 能力档案承载。现有 8 条 CRE 规则(背板线缆 derive + CPU/内存/GPU 互斥 exclude)已到有用边界。详见 [[strategy-center]]。

**待办（⚠️2026-10-22 用户定调放弃，以下不再计划做，留档仅防重复提议）**:
- 海光 KH-50000 series 归属:系统 series=[Orion/Polaris/Intel/工作站] 无海光,Z 系列暂挂 Polaris,是否单列待定
- 内存速率分档(spec_rules):随 CPU SKU(AMD 9004=4800/9005=6400、海光 5600),待权威 MT/s 对照入 reasoning_flow_repo spec_rules
- 数据清理:id=21(名字 Polaris/series Orion/bays12/孤儿)、id=24(4.5U 直通孤儿)、id=26(4.5U Switch,疑似 id=25 重复);id=22 ZSA24V2-P gpu_arch=pt 但真实海光4U=Switch,建议改 switch
- 后面板件料号(Riser/OCP 带 io_slot/option_type specs)parts_master 仍为空,backfill_rear_specs.py 缺失,待录入
