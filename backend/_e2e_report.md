# E2E 报告 · 演练流试运行验证

- 时间：2026-10-31 02:56:22
- 角色：support_engineer
- 结果：✅ 完成，共 1 轮

## 指标

- scenario：演练流试运行验证
- finished：True
- turns：1
- wall_s：22.6
- turn_s_min：22.6
- turn_s_max：22.6
- cards：0
- repeat_cards：0
- repeat_rows：0
- repeat_cats：0
- auto_answers：0
- kp_rows：None
- assembled_rows：None
- last_step：output
- pause_events：0
- pause_kinds：[]
- pause_reason_codes：[]
- pause_facts_incomplete：0
- pause_kinds_unknown：[]
- interrupted：False

## 暂停 / 断点

- （本次没有中断点：全程未触发 pause 广播）

## 轮次 1（22.6s）
- 输入：帮我分析一下当前商机的平台分布情况
- 旁白：数据范围：2025.01.01 ~ 2025.06.30（status 排除 ai_office/deleted；平台口径与商机线索页一致）

一、窗口内平台分布

按累计口径（数据范围整体），平台分布查询结果为空，未能取到各平台商机数与占比数据。

可用的平台维度数字如下：

| 口径 | Polaris | Orion | 合计 |
|---|---|---|---|
| 本周新增商机 | 8 | 3 | 11 |
| 本月新增商机 | 29 | 9 | 38 |

从新增口径看：本周 Polaris 占比约 72.7%、Orion 约 27.3%；本月 Polaris 占比约 76.3%、Orion 约 23.6%，Polaris 持续占主导（占比为基于工具返回数字的计算值）。

二、其他说明

- 窗口累计 KPI：累计商机 224、累计配置 542；但逐月序列与累计平台分布未返回
- 引擎 input：需求原文 17 字
- 引擎 agent：商机趋势分析报告 · 527 字
- 引擎 output：已交付 · 527 字
