---
name: skill-real-run-2026-09-07
description: 【史料】09-07兆芯全流程实测快照：37分钟9轮/丢行/池三病灶——所有病灶已随后续P0~P6轮次修复；当前态看skill-current-state-2026-09-12
metadata:
  node_type: memory
  type: project
  originSessionId: 76f3ccd4-bf0d-4da8-a670-0aa255890b24
  modified: 2026-09-12T10:03:31.079Z
---

**本文是史料（09-07 快照），不再是「必读」。当前态权威 = [[skill-current-state-2026-09-12]] + docs/需求分析/01_架构与契约/需求分析skill-技术架构.md。** 病灶→结局对照（09-12 核验）：

| 09-07 病灶 | 结局 |
|---|---|
| 硬盘 3 行丢 2 行、网卡缺口无声消失 | ✅ 已修：P3 行身份（origin 铸 row_id）+ 09-12 归属收口；回放 43 线程重复/丢失=0 |
| 收尾文案虚报「未匹配0件」 | ✅ 已修（P0-P6 机制文案收口） |
| 兆芯检索不到 KH | ⚠️ 半修：靠通用「≥3 位数字串子串」命中（KH50000⊃50000），非映射表；中文口语词（万兆/千兆/智铠/核显）仍零召回=现存缺口 |
| DDR4 混进 DDR5 池、request_spec 没编译成 spec_filters | ✅ 已修（09-12 实测 DDR4/DDR5 不再混池；required_specs 通道在用） |
| 池=类目全量 limit 截断 | ✅ 已修：progressive disclosure，大脑逐行按需 query_parts |
| 超时行落引擎兜底卡、每答全量重跑 | ✅ 已修：单 agent 长循环+步进闸门+P2.5 单轮墙钟上限/零产出失败出口 |
| 37 分钟 9 轮 | ✅ 大幅改善：同场景 09-11 复测 3 轮/171s |

09-07 实测细节（历史数字）：真实兆芯需求 preview 线程全程 37 分钟 9 轮；登记 27s、点选快速路 10s、KP 轮 37~198s；机型/CPU/内存/RAID 当时已正确（9361-8i 正确传播 SAS 线缆）。「毛线实证」结论仍有效：大脑智能在场（KH50000 语义匹配、RAID 教科书级选项），瓶颈在管道不在模型。

当日重构（run_skill_agent_turn 单 agent 执行器/begin_step 步骤协议/final_gate 终检/SkillStudio 三栏/砍 render_skill_manual 与节点抽屉 AI 层、AI 指令唯一入口=左栏「任务规则」manual_rules）已全部落地并被后续 P0~P6 继续演进——细节以技术架构文档 §5/§19 为准。相关：[[skill-tree-trunk-architecture]] [[skill-latency-program]]
