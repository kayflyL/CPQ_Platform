---
name: kp-spec-coverage-sparse
description: KP 料号库 spec 覆盖：2026-07-25 8%→89%(name提取+型号对照)；2026-08-05 硬盘专项 2维→5维(+Media/Form Factor/RPM)100%；剩 GPU/CPU 国产卡留手填
metadata: 
  node_type: memory
  type: project
  originSessionId: 2ff1ea54-a82f-4574-a36b-29a4b4d0e977
  modified: 2026-08-10T09:41:03.604Z
---

KP 模块 `kp_part_specs`（EAV 表：part_id+spec_key+spec_value，一行一键值对，非 JSONB）曾严重稀疏（8% 覆盖）。**2026-07-25 两轮补齐到 89%（200/225）**：

**轮 1：`backend/scripts/apply_extract_specs.py` 从 name 正则提取**（回滚 `id > 45`）
- 100% 覆盖：HDD/SSD(Capacity/Type)、Memory(Capacity/Type/Speed)、Network(Link Speed/Ports)、Raid card(Cache/Ports)

**轮 2：`backend/scripts/apply_lookup_specs.py` 型号对照表**（回滚 `id > 361`）
- GPU 57%→71%、CPU 34%→59%
- 对照表是脚本里的 `GPU_VRAM`（4090=24G/5090=32G/L40=48G/H100,A800=80G/W7900=48G）+ `CPU_CORES_TABLE`（9334,9354=32C / 9554=64C / 9654=96C，均经 name 其他变体印证）；外加 CPU name 增强规则（匹配 "48 cores"/"32 core" 单词写法，原 `\d+C\b` 漏了这个）。

**剩 25 件留手填**（故意跳过，填错比留空危害大）：
- 国产 GPU 10 件（壁仞/沐曦/天数智芯/武桐树/曦云/智铠——训练数据不可靠）
- Intel Xeon 4 件 + 不确定 AMD 型号 11 件（7A23/9255/9347F/9355/9124/9745/9J14，无 name 印证）
- Bridge/HBA/NVSwitch 各 1 件（name 无规格语义）
- 用户给规格书后，往 `GPU_VRAM`/`CPU_CORES_TABLE` 加条目重跑 apply_lookup_specs.py 即可（逐 key 补缺，不覆盖）。

---

**2026-08-05 硬盘专项治理（HDD/SSD `category_id=2`，52 条）：2 维 → 5 维 100%**

原只有 Capacity/Type（47-48/52），补全到 Capacity/Type/Media/Form Factor/RPM 五维全部 52/52。
- **新增维度**：`Media`(SSD/HDD)、`Form Factor`(U.2/M.2/2.5"/3.5")、`RPM`(7200/10000/15000，仅 HDD)。
- **Form Factor 42 条 name 没写**，按用户拍板的常识默认推断（NVMe→U.2、HDD→3.5"、SATA/SAS SSD→2.5"）；推断值在 DB 里就是普通 `Form Factor` 值（不区分来源），42 条推断件 id 清单已交用户复核，管理面可改。符合 [[derive-must-have-manual-fallback]]「默认值+可手填」。
- **Media 推断铁律**：NVMe 协议→SSD（物理必然）；TLC/QLC/SLC→SSD。
- **RPM 只填 name 铁证的 3 条**（2.4T 10K/15K、20T 7.2K）；9 条 HDD name 无转速、留空待手填（不瞎推，转速 7200/10K/15K 都可能）。
- 顺带 P1：补 5 条规格残缺件（id 261/256/264/260/263，name 铁证解析）、name 归一 14 条（NVME→NVMe、双空格、中文后缀前补空格；不动形态写法）。
- 最终分布：Form Factor {U.2:20, 2.5":17, 3.5":12, M.2:3}；Media {SSD:40, HDD:12}；Type {SATA:25, NVMe:23, SAS:4}。三维度交叉自洽（NVMe23=U.2 20+M.2 3；HDD12=3.5" 12）。
- **applicable（适用机型）刻意不填**：硬盘选型应由 Form Factor↔机箱背板槽类型对接，而非逐盘填 applicable；51/52 件无 compat 是合理的「硬盘通用」。机型适配是功能开发，不是数据清理。
- 直连库治理流程（可复用）：备份 JSON 快照 → dry_run 打印 diff 预览 → 单事务写库(116 INSERT+14 UPDATE) → 写后只读校验覆盖率/分布/交叉自洽。备份在 `backend/tmp_hdd_backup.json`（21KB，可回滚）。

spec_key 全集（按覆盖件数）：Ports/Capacity/Link Speed/Type/Speed(17)/Cache(14)/Cores(约17)/tdp(6)/cables_per(2)；硬盘专属 Media/Form Factor/RPM(52/52/3)。

**Why:** 历史导入只录 name/价格/SKU。与 [[derive-must-have-manual-fallback]] 同源——结构化维度供编辑/兜底，name 不该当规格书用。

**How to apply:**
- 写入策略 = **逐 key 补缺**（已有手填 key 不覆盖），格式带空格（`16 GB`/`1.92 TB`，不能无空格否则比价矩阵按 Capacity 分组分裂）。
- **新盘导入按 5 维填**：Capacity("N TB"/"N GB" 带空格)、Type(NVMe/SATA/SAS)、Media(SSD/HDD)、Form Factor(U.2/M.2/2.5"/3.5"，name 没写就按 NVMe→U.2/HDD→3.5"/SATA·SAS SSD→2.5" 默认)、RPM(HDD 才填，name 无据则留空)。
- 凡依赖 spec 聚合的功能（比价矩阵、spec-facets 下拉）仍要保留空态兜底，应对 0% 分类（Bridge/HBA/NVSwitch）和 GPU/CPU 未填的件。
- 比价矩阵可用维度：HDD/SSD 5 维全开、Memory 有 Capacity/Type/Speed、Network 有 Link Speed/Ports、Raid 有 Cache/Ports、GPU 有 Capacity(显存)、CPU 有 Cores。

---

**2026-08-10 进展：8/6 后录入的 16 件全缺 specs 已补齐（70 条 spec，0 件仍缺）。**
- 13 件 name 确定性解析（硬盘 5/内存 2/网卡 5/RAID 1），3 件 GPU 用 **WebSearch 联网查**（非 Firecrawl——旧 Firecrawl 脚本已删，见 [[firecrawl-spec-extract-poc]] banner）：RTX Pro6000 96G(11维)/AMD R9700 32G(10维)/天数智芯天垓150(5维，国产卡也能查到基本规格)。
- 脚本 `backend/scripts/backfill_missing_specs.py`（dry-run 默认 / `--commit` 写库；复用 kp_repo 的 `_i*` 解析函数 + `update_part`）。**可复用**：以后新批次缺 specs 改 `created_at` 范围重跑（update_part 全量替换、幂等）。
- 格式/推断规则**完全沿用上文惯例**：带空格(`960 GB`)、Form Factor 默认推断(NVMe→U.2/SATA·SAS SSD→2.5″/HDD→3.5″)、RPM 只填 name 铁证(269 的 4TB HDD 无转速留空)、CUDA Cores 仅 NVIDIA 填(AMD/国产卡不套用)。
- 验证：16 件 70 条 spec 写后 0 件缺；`pytest -k kp` 43 passed（补 specs 不破 part_identity_key）。
