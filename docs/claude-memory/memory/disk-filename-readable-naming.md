---
name: disk-filename-readable-naming
description: 用户定调落盘文件名走「原始名+短UUID」（build_object_id），放弃纯 UUID 完全防孤立设计；存量不迁移
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f7b00462-3f82-4676-8b7e-818336c9c8f2
  modified: 2026-07-27T03:10:53.332Z
---

商机存档文件落盘的 storage_key 命名规则：`{清洗后的原始stem}_{8位uuid}{ext}`，由 `backend/app/services/storage_adapter.py` 的 `build_object_id(original_filename)` 生成。清洗保留中文/字母数字/`()[]-_`，空格和危险字符（含 `..` `/`）压成单 `_`，截断 40 字符，兜底 `file`。短 UUID 用 `uuid.uuid4().hex[:8]`。

**Why:** 用户（运维视角）直接看 `storage/opportunities/{opp}/` 磁盘目录时，纯 UUID 名认不出是哪个文件——明确诉求。原始名仍存 DB `opportunity_attachments.original_filename`，UI 列表/下载都还原成原名，所以「改名」只影响磁盘实体可读性。短 UUID 后缀防同名冲突；opportunity_id 本身稳定（不像 sales/chassis 业务字段会改名），所以放弃纯 UUID 不会让文件孤立。

**How to apply:** 新增任何走 StorageAdapter 的文件落盘，object_id 用 `build_object_id(original_filename)` 而非 `uuid.uuid4().hex`。存量的纯 UUID 文件**不迁移**（止血，等自然淘汰）。excel 上传生成报价单的源文件也走同一通道：`quote.upload_to_opportunity` 解析成功后 `save_bytes` 落盘 + `FeedRepository.add_attachment`（kind=upload, category=technical 对应存档区"方案/详细报价"桶, quotation_id 关联）+ socket broadcast；不再走 `_temp/`（24h 会被清掉）。
