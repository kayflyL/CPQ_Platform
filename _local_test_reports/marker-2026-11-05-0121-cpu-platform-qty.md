# 标记 2026-11-05 01:21 · Polaris 机型推荐 Intel CPU / 数量仍默认 1 / 选项过多与顺序

线程：`a0c42a07d28149f48801f07c4b23f74f`（平台 Polaris、机型 ZS220 V2 已确认锁定）

## 现场实锤

- `ext.confirmed_slots`: platform=Polaris + server_model=ZS220 V2；locked_baseline 规格明示
  「最多 2 颗兆芯开胜 KH-50000」。卡上 CPU 候选却是 Intel 8558/6530P/6544Y。
- **标记 1 根因=数据**：CPU 料 `applicable.series` 20 条漏标（Intel/AMD=None→按「通用件」
  放行任何系列）；KH 系列正确标 Polaris、部分 EPYC 标了 Orion。平台过滤机制（_SeriesScopedRepo）
  本身工作正常，是漏标数据穿过了它。Intel 8558 这个行本身来自**抽屉目标层的预置行配置**
  （origin=cfg:，业务数据里写死了 Intel 例子）。
- **标记 2 根因**：行配置全部 qty=1，数量住在 spec 文本（「2 颗」）里——行申报量没用上；
  大脑的 recommend 其实带了正确 qty（内存 8 条），但行卡数量取的是行申报量。
- **标记 3**：_row_pick_options limit=8；行卡顺序=抽屉行配置顺序（CPU 排第 3/4）。

## 处理

1. **数据（待用户执行）**：迁移 SQL `backend/migrations/20261105_tag_cpu_applicable_series.sql`
   ——20 条 CPU 料补 `{"series":["Orion"]}`；回滚备份
   `D:\CPQ_Archive\kp_cpu_applicable_backup_20261105.json`。批量改库被权限拦截，等用户点头。
   另需用户把抽屉行配置里的「Intel 8558」等改为平台中性表述（如「处理器 2 颗，按机型平台适配」）。
2. **行数量解析（已改）**：_row_qty 从行 spec 文本确定性提取申报量（2 颗/4 条/2 块→2/4/2），
   显式 qty 不覆盖；仍无则采信未过期的大脑推荐量。离线验证 5 例全过。
3. **卡面候选 8→4**（已改）：其余候选走「从配件库自选」下拉（limit=50 不变）。
4. **行卡顺序跟抽屉必配类目序**（已改）：稳定排序，CPU 在抽屉里排前面就先问；
   离线验证 CPU 升到第一。
5. 后端已重启无错。

## 未覆盖边界

- 漏标数据修完前，Polaris 机的 Intel 行召回仍可能为空（行无卡→大脑下轮重规划）——
  数据修正是根治。
- 抽屉行配置（Intel 8558 等 17 行）是业务数据，由用户改平台中性表述。
