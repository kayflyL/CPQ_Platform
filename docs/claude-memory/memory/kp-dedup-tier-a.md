---
name: kp-dedup-tier-a
description: "KP 配件库去重：08-05 一轮 220→158；09-19 二轮 287→186(101 alias 合并,判据改最新价比<1.3)+spec 补齐19件+脏值修复；脚本 kp_dedup_*.py 可复用"
metadata: 
  node_type: memory
  type: project
  originSessionId: da0c6331-3012-463a-a1df-4335e838d714
  modified: 2026-09-20T07:30:31.654Z
---

KP 配件库"一物多码"治理(2026-08-05)，共减 62 件(220→158)。判据从「归一名」演进到「spec-identity + 价格簇」。

**同一性判据 `part_identity_key(name, category, specs)`**（kp_repo.py 模块级，导入去重/合并共用）
- HDD/SSD：`(Capacity, Type, Form Factor, Media, gen, workload, rpm)`，spec 主导；形态无标注按企业盘默认推断(NVMe→U.2/HDD→3.5"/SSD→2.5")。
- 核心：已结构化维度的冗余标注(SSD/U.2/形态)被 spec 吸收 → 同件；真差异词(gen4/工作负载/转速)从 name 提取保留 → 不同件。
- 其它品类：归一名(lower + 去空格 + **标点周围空格归一** + 容量单位归一)。
- 单测：backend/tests/test_kp_identity.py（18 例）。

**多轮合并**（均：搬引用 + 价格史并 canonical + 删 alias；价格合并校验 canonical 史=组内总和）
- **Tier A**（纯录入重复：大小写/空格/标点/同名）12 组 → 220→208。
- **Tier B**（硬盘冗余变体：SSD/U.2/形态冗余）6 组 → 208→195。spec-identity，M.2/U.2·HDD/SSD 不误合。
- **NIC 语义**（7 组 → 195→164）：光模块在该库**非计价因素**（同规格±光模块同价：25G 双口全 ¥1200、10G 全 ¥950-1500），故 ±光模块/光口/CX4·CX5/裸卡 = 同件描述噪声 → 合；价格偏离(高级型号/异常)留。canonical name 去芯片噪声取通用("25G 2port+光模块")。
- **硬盘 gen4/工作负载复查**（6 组 → 164→158）：按价格判据，3.84T gen4(×1.09)合、1.92T gen4(×1.79 真·贵)留；企业级/读密集型多数同簇合，480G(×1.45)留。

**统一价格判据（举一反三）**：同规格 + 价格 max/min < 1.3 → 合；> 1.3 留（真不同件/异常）。已留：1.92T gen4、480G 企业级/读密集、200G 标 ¥1200 异常、400G NDR ¥11799/17399、25G IB/RoCE+100G光模块 ¥2030、ConnectX-6 Dx ¥1770。

**09-19 二轮（287→186，删 101 alias）**：08-05 后新导入又堆积（specs=0 的 410-430 批+运营换措辞重录）。本轮沉淀：- **判据升级**：全史价比会被时间漂移污染（3.84T NVMe 4月9500→9月13052 是涨价不是不同件）→ 改用**最新价比<1.3**；同件价随月份波动属正常，历史行照搬保留。
- 用户定调价格合并规则：**不同日期的价格行并到保留件下；同日期撞车保 canonical**（alias 同日他价丢弃，如 960G SATA 297 的 4700@08-12）。
- 合并时 alias spec **逐key补缺前先归一脏值**：Media/Type 词表错位（Media='SAS'、Type='HDD'）、DIMM Type/Type 填反（DIMM Type='DDR5'）、接口塞芯片名（接口='CX6'）、SFP28 解析成 Ports='28'。
- **kp_part_search_index 也引用 part_id**（1:1 向量索引）：删 alias 行 + bump canonical updated_at，freshness_drift 对账自动触发重建重嵌（part_search_index.py 自愈机制）。
- 保留不合并：480G 企业级/读密集(08-05裁决)、25G CX4 1650 vs 800、9560-16i 1.5万 vs 8.6千 两档、CX7 400G 11799/17399、10G 4port PCIE半高 3240 异常、600G SAS SSD vs HDD(spec 媒介不同价近也不合)。
- spec 三轮补齐（scripts/kp_spec_backfill_20260919.py）：19 件 name 铁证+惯例默认，EPYC 9455/Xeon 8558/Xeon 6530P/昆仑芯 P800 联网核实后填（P800=96GB HBM3/XPU-P/PCIe4.0）；修 'AMD EPY  9455' name 笔误；'RAD card' 分类并回 'Raid card'。
- 备份：backend/tmp_kp_merge_backup_20260919.json + tmp_kp_spec_backfill_backup_20260919.json（parts/specs/prices/bom_lines 全量，可回滚）。
- **同日补漏（merge2+merge3，287→186→174→173）**：做报价匹配时用「族内 semantic token 集相等」扫描又揪出 20 个漏网（5090 涡轮卡×3、AMD EPYC 9654 96C、昆仑芯 P800×3、智铠100DUO×5、沐曦/曦云 C500、9560-8i 4G 含超级电容、480GB/960GB SATA 变体）；教训=粗键调查有盲区，**「语义 token 集相等/子集」本身就是最强的重复信号**，可作为下轮去重的首选调查法。备份 backup2/backup3 同目录。
- **报价侧同一性有三条链路，缺一不可**：①上传 enrich 阶梯（pricing_engine.enrich_item_prices）②工作台显示/历史（/quote/kp/history → kp_repo.get_price_history，曾是 `name==model` 硬等，用户实测兆芯KH-50000 96C 仍判新部件才暴露）③价格入库（insert_price，精确名找不到就建新件=重复件出生通道，现默认关但手动「入库新配件」在用）。已统一走 `kp_repo.resolve_part`（精确名→归一名→族 identity→语义 token，category 传 part_category 做家族限定）；改匹配只修一条链路=白修。
- **语义 tokenizer 实战坑**（09-20 用户实测暴露）：端口词紧贴速率会粘连（双口25G→2port25g，端口词替换必须两侧补空格）；噪声词是滚动补充的——cache/IB/RoCE/RDMA 都是报价行常见冗余，用户上传名还带任意需求后缀（"(需要CX6)"，中文自动落 token 无害）；用户点「入库新配件」会把坏匹配固化成重复件（431/432 已并回），修好匹配后要扫 created_at 清理测试期新件。
- **嵌入召回层：试过并当日回退**（09-20）。做法=resolve_part 第五级（fastembed bge-small-zh 查询向量 vs kp_part_search_index 余弦 + 数字 token 硬否决 + floor0.78/margin0.05），离线校准很干净（349 历史报价行文本+3反例：12 命中/0 事故、反例全阈值全拒）。**但实测本机单条查询推理 1.6~3s**（方案预估几十 ms 错了一个数量级以上），而 resolve_part 在报价工作台加载的请求热路径上（每行一次 /kp/history），一页未匹配行=几十秒——用户当场叫停（「大模型功能别进匹配」），已整删（函数+接线+测试，非注释保留）。教训：**任何模型推理（哪怕本地小模型）不进请求热路径，除非先实测单条延迟**；若将来要召回，出路是离线批处理（如夜间把历史报价行预匹配好落表）或秒级以下推理 runtime；阈值结论（floor0.78/margin0.05，数字token否决，12命中/0事故）记录在此备查，诊断脚本已随退役删除。GHz 归一同日保留（2.6GHz→2.6 对齐 spec 裸频率，纯 tokenizer 零推理，让 64C 2.6GHz 类行在语义层即命中），前端 partNameMatch.ts 同步。
- 遗留：bom_cases 3 处死引用 part_id=62（历史删除遗留，非本轮造成）；NIC 全史价波动大（460~1810）靠最新价判断。

**合并方法(共用)**：canonical = 价格史最丰；删 alias 前搬 `rules.bom_cases.kp_lines`(JSONB part_id，**不级联**，手 UPDATE) + `kp_price_history`/`kp_part_compat`/`kp_part_related`(级联；price_history 先搬，compat/related 处理 unique/自环)。**价格合并必校验**：canonical 史数 = 组内合并前总和。
**part_id 引用源全集**：bom_cases.kp_lines(JSONB) + kp 4 级联表；quotation 快照不引用 part_id。

**导入检测升级（源头防范）**：`find_parts_by_dedupe_key(oem_sku, name, category)` 三层匹配(oem_sku → name 精确 → 同 category identity)；classify 传 category_name。上传不再因大小写/空格/冗余词建新件。

**detect_duplicates 09-20 重写**（`_duplicate_groups` 纯函数 + IO 薄壳，单测 test_kp_duplicates.py 18 例）：六层信号 SKU精确1.0 > identity键0.95 > token相等0.9 > 子集+价格簇<1.3→0.8 > 子集0.7 > 名称相似≤0.69（difflib 封顶防淹排序）；**brand 分桶已删**（改 category 分桶，旧盲区=同件 brand 不一致）；**聚组只用强信号≥0.8**，弱对独立成 2 件组（防同类名经并查集级联成 38 件巨组，旧代码同病被 brand 桶偶然掩盖）；**数字 token 一侧独有即否决弱信号**（EPYC 9xxx 同前缀刷屏教训）；子集要求双方 token≥2。真库 173 件 → 29 组/69 件，抓出旧机制盲区（语序变体 NVME SSD 1.92T、PRO5000 连写差、3.84T 簇）。reason 改 reasons 列表 + price_ratio/price_warning 组头警示，仍 display-only。

**未做**：NIC 补结构化 spec(速率/端口/芯片/接口/光模块，现全在 name)；canonical 别名机制(软合并)；Tier C(spec 同但确不同型号，靠 oem_sku 区分)。

**Why:** 旧导入 name 精确匹配 + 运营按"速率+端口"报价不分光模块/芯片，累积一物多码。
**How to apply:** 合并前查 bom_cases.kp_lines 引用；判同件用 part_identity_key + 价格簇(别裸 name==)；光模块/CX4·CX5/企业级 在 CPQ 报价场景按价格判同件。关联 [[kp-spec-coverage-sparse]] [[derive-must-have-manual-fallback]]。
