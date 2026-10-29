---
name: kp-import-merge-playbook
description: "往 KP 配件库导入运营价格清单(非标准 Excel)时的处理范式:转换+dry_run+去重,别直接导"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0f3d8d2b-b9df-4f34-9c71-5fecec221218
  modified: 2026-07-23T09:36:06.176Z
---

往 KP 配件库导入真实运营价格清单(如 `Key Parts_cleaned.xlsx` 那种非标准表)时,绝不能直接喂给导入功能 —— 先转换、比对、去重。

**Why:** 这类表列名跟导入模板完全对不上(描述/金额/报价时间/Key Part),且同一型号多次报价、分类名跟 DB 已有分类不一致、name 有大小写空格变体、还混脏数据(H100 价格少个零、空价格)。直接导会:全行 invalid、分类分裂、建成重复件、价格历史翻倍。用户明确"担心数据库变乱",接受度是「宁可多一步转换,不要污染」。

**How to apply:**
1. **转换层**(一次性脚本,不入库):列重命名(描述→名称、金额→价格、报价时间→价格日期、桃红备注→价格备注);分类映射到 DB 已有名(如 NIC→`Network(NIC) requirement`、RAID Card→`Raid card`,见 DB 现有分类);手工核对的大小写/空格变体映射到 DB 已有 name;空价格 + 明显错价整行跳过。
2. **dry_run 先行**:出 new/update/conflict/invalid 预览,按"件"口径解读(dry_run 的 new 是行数,同件多行会夸大)。
3. **脏数据让用户拍板**:价格准确性影响报价系统,不能擅自丢/改数值(用 AskUserQuestion 问:错价跳过/照导/给值;空价建件/跳过)。
4. 真导入前确认 `price_duplicate` 机制生效(DB 历史价格大量来自同类表,去重会拦下重复)。

**别对 name 做激进大小写归一化** —— NVME/NVVe 这种字母大小写差异保守留着,误并不同型号比留着重复件代价大。后续在配件页手动合并即可。

相关:[[kp-parts-unification-roadmap]]、导入功能实现在 `backend/app/services/kp_import_export.py`(列别名/价格去重/会话级防重复建件)。
