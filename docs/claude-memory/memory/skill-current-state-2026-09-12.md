---
name: skill-current-state-2026-09-12
description: 需求分析skill当前态权威快照(09-12实测核验)——权威文档指针+原生FC/9工具/真实表持久化/实测基线/已知未修+我09-12检索层实测病灶；碰skill前先读（取代09-07实测记忆的「必读」地位）
metadata: 
  node_type: memory
  type: project
  originSessionId: 5775d953-5cfd-4007-99ef-3a6462fb8acd
  modified: 2026-10-12T03:05:33.776Z
---

**权威现状源 = `docs/需求分析/01_架构与契约/需求分析skill-技术架构.md`（维护到 2026-09-12 当天，§0-25 全景）。碰 skill 任何改动前先读它，别靠记忆推断——本文只是快照+指针，文档为准。** 09-12 已用代码/DB/实测三路核验过记忆与现状的差距，历史实测见 [[skill-real-run-2026-09-07]]（已降级为史料）。

## 09-13 模拟用户 9 场景电池（用户批准，全档案在 backend/_sim_results/）

| 场景 | 结果 | 轮/墙钟 |
|---|---|---|
| A1 极简口语（虚拟化） | ⛔12轮未完 | 12/1602s |
| A2 AI训练推荐式 | ✅ | 2/45s |
| A3 挤牙膏分轮 | ✅ | 4/90s |
| B1 AMD详细单 | ✅ | 3/65s |
| B2 存储大盘位 | ✅ | 2/52s |
| C1 同规格补充（D1考题） | ✅ 内存仍一行×16 | 2/55s |
| C2 改口纠正（D1考题） | ✅ 8T×4替换6T×6 | 4/242s |
| D1 B200库外复测 | ✅（旧基线7轮426s） | 3/80s |
| D2 闲聊问价 | ✅ 价格纪律三轮一致拒答 | 3/81s |

全局零重复卡/行；规格补全生效（25G网卡/9560-16i 4G缓存/16T/Pro6000 库内命中）。
**发现的问题（未修）**：
- **P1 平台冲突调解半途而废（C2）**：机型平台≠配件平台时，scope 真话机制正确触发+旁白给了三选一（换CPU/换机型/保持原需求），但实际弹的卡是 KH50000 核数选择卡（旁白与卡不一致），点选后 Orion 机型+Polaris-only CPU 直接落锁，冲突未真正解决；旁白还错称 ZS25V2-P 是 Polaris 平台。修法方向：冲突行的卡必须承载三选一方向，或 select_parts 落锁前校验 applicable_series vs 机型平台。
- P2 极简输入逐卡链太长（A1）→ **09-13 已修通（端到端 3 回合收口）**。根因链（提示词修不了的引擎级缺口）：①select_parts 的 new_row 铸行通道大脑不知道用；②specified=false 只能写 KP_RECOMMEND 永远不能锁；③锁定唯一通道=单选项单 pick，「全部按推荐」装不下多颗。修法四件全落地：(a) ask_user 选项 pick_all 标记（agent_tool_specs schema + skill_tools_misc 留底）；(b) 信号 kp_accept_recommendations→slot_contract.apply_structured_slots 把 KP_RECOMMEND 批量晋升 KP_PICKS（点击=亲口确认多行版）；(c) **信号双出口收口**——引擎缺口路 ask_option_signal 与 done 兜底路 _emit_ask_card 原是两套各自实现的选项→信号解释，已漂移（pick_all 只加了兜底路，A1 走引擎路点击 signal 永远 None、死循环 12 轮）；现 _emit_ask_card 只做行身份解析后转交 ask_option_signal，全链路唯一出口；(d) DB flow 125 规则15 教大脑「query_parts 查齐→逐行 new_row 铸推荐→ask_user 整体卡（pick_all）→点后禁再发卡」。**A1 复测：finished/3 轮/229s/kp 16 行/组装 25 行/last_step=output**（修复前 9~12 轮死循环）。测试：tests/test_kp_bulk_accept.py 5 例+全量 634 绿。e2e 日志在 backend/_sim_results/a1_fix.log。
- **P2b 整单委托已落地（09-13 同日，用户定调「不然系统一点智能性都没有了」）**：客户原话明示全权委托（「一切你定/完全按推荐/你看着配」）时大脑经 `fill_requirement(delegation="full")` 申报（只认申报不猜）→ `slot_contract.blanket_delegation(ext)` 使 `unconfirmed_premise_fields` 放行（推断的类型/平台/机型步不再逐项出确认卡，复述里说明依据）→ 确认收敛到整体落定卡：大脑把代定类型/平台写进 desc 首行（规则15/19），点击时 `skill_chat` 钩子调 `confirm_registration_on_bulk_click` 把目录字段快照进 confirmed_slots（机型维度除外），改值即失效重求证。**A1 委托版 e2e：2 轮/1 卡（仅整体卡）/144s/finished/21 行组装**（对照非委托基线 3 轮 2 卡 229s）。测试 tests/test_delegation_full.py 4 例+全量 638 绿。场景文件 scripts/e2e_sim_a1_delegate.json。见 [[inferred-slots-must-confirm]] 豁免条款。
- **左栏任务规则压缩重写已落地（09-13 晚，用户嫌 4314 字太冗余、拍板争取 1200 内）**：24 条 4314 字 → **11 条 1217 字**（DB 流 125），重编号 配件15/前提19/登记13/价格20/收尾24 → **7/8/6/10/11**。方法=机制细节退给工具契约（select_parts/ask_user/inspect schema 原生 FC 每轮可见），规则只留编排与纪律。**三个教训**：① 宪法 test_constitution MOVED_RULES 钉了 20 个锚点短语必须原样保留（改写措辞即红）；② 「选最接近的**或**让客户点选」「多盘组/GPU 组逐行列出」这类半句是行为承重墙——砍掉后 A1 实测 3轮2卡→5轮4卡+盘组单档，恢复两半句即回 3 轮 2 卡；③ 压缩后必须 e2e 复测（A1 3轮2卡100.7s / 委托版 2轮1卡72.6s 双达标，比压缩前还快一倍）。备份：backend/_sim_results/manual_rules_backup_20260913.txt（原版）与 manual_rules_1200.txt（现版）。
- **自选配件通道回归（09-13 深夜，用户实测报告「自选下拉+调数量没了」）**：机制未删（enrich_ask_gap/stuck_gap/AskCard/cardPick 全在），根因=P2 批量流快乐路只剩整体卡、行卡不再出现，自选是逐行问卡流的副产物。修法三件：① `_KpNode.extra_ask_options` 对带 pick_all 的整体卡结构性注入「我自己逐项挑（自选料号/数量）」（无信号选项→点击落 ask_answers 口头回答），大脑按规则 7 逐行 ask_user(row=…) 发行卡→parts_card 下拉+数量回归；② **select_parts `part_required` 契约错误**——new_row 只给 category+spec 不给料号名时曾走到 hit=None 崩 AttributeError、整次调用报废（同批已铸行被丢回、下轮重铸循环），现行契约校验后早退白盒错误指向 fill_requirement(kp_rows)；③ **phase_kp_reason 归属收口放宽**——原按 registration_owned_categories 全量过滤属主类目声明行，AI 铸的推荐行（客户没提 CPU/内存）下一轮即被丢弃（自选流无 pick_all 晋升，行消失→重铸循环第二根因）；现改为「登记表已有该类目行才让位」，cfg: 行随 KP_CONFIG 持久。**e2e 复测**：自选场景 10 轮 229.9s 收口（9 卡全行绑定 kp-xxx 稳定身份、CPU/内存/盘/RAID/网卡点击全带 kp_manual_pick 落锁、5 配件行 14 组装行）；委托版回归 2 轮 1 卡持平基线；A1 标准版 7 轮 6 卡（基线 3 轮 2 卡）——4 张字段确认卡系 LLM 抖动+第 6 轮整体卡重复一次（放宽后大脑多铸的行须再落定，行为正确但话痨，观察项）。左栏规则 7 同步加「客户要自己挑→逐行 ask_user 带 row 发选件卡（候选系统自动补）」+「new_row=true 带料号名铸推荐」，1260 字。测试 test_kp_bulk_accept.py 6 例+全量 666 绿。场景文件 scripts/e2e_sim_a1_selfpick.json（max_turns=15）。
- **配件数量步进+AI带数量推荐已落地（09-15，用户实测「能选料不能调数量/AI只推型号不推数量」）**：根因三层——①ask_user 选项白名单不带 qty/qty_max；②`_ask_gap`/`_emit_ask_card` 重建卡选项时丢弃；③前端 AskCard 步进器只认**初始卡选项**的 qty/qty_max（下拉候选带也不算，`adjustable` 只看 question.options）。修法：`skill_phases.baseline_qty_cap(category, baseline)` 共享映射（GPU→gpu_slots/Memory→max_dimm/HDD·SSD→bays/CPU→max_cpu，无边界或未登记=0）；`_KpNode.enrich_ask_gap` 是收口点——全卡选项 setdefault qty(=行申报量)/qty_max(=物理边界，无边界退 24，永远≥申报量)，pick_meta 随卡留底能力字段；stuck_gap/_row_pick_options/card-pick 端点同口径。大脑侧：`bridge_ctx` 摆桌 `kp_baseline_caps` 事实块 + select_parts 落 pick 时物理上限闸（qty_over_capacity 拒超界，逼换大容量条）+ ask_user/select_parts 契约加 qty 字段说明。点击数量收口 `_signal_with_qty` 的 kp_manual_pick 分支从裸 999 改按类目能力 clamp。死码 `_row_qty_hint` 已删。测试 test_kp_stuck_gap 4 新例+select 闸 1 例，全量 715 绿。宪法坑：工具 description 里写「由系统」三字会被 PROSE_MARKERS 拦（机制指令唯一出处=左栏），描述只写参数事实。
- P3 旁白复读/自相矛盾：同句重复2-3遍（A1）；同轮先9355后9335（A3）；复述问确认+已登记同轮挤一句（B2）。疑似 S3 双段指令副作用。**09-13 A1 复测更严重：单轮内报了三套互相矛盾的推荐配置（9654/768G→9354/512G→9354/1T），268s 一轮**——批量落定前 prompt 还须加「一次推荐只出一版」。
- P4 server_type 推断落槽口径不一（A2「AI训练」直落没弹卡，A1/D2 弹了）——rule 19 执行方差。

## 09-13 五项拍板收口（用户全按推荐方案批）

- **D1 行归属纪律已落地**：左栏 manual_rules 规则 13 追加（DB 流 125，3596→3734 字，update_manual_rules 不升版本）——同类别补充优先并入原行（同规格一行），不同规格组合（1G×4 与 10G×2）才开第二行+说明理由；引擎层维持不归并。
- **D2 kp prompt 20k 上限：不动**（等配件规格补全后复测，数据质量改善自然减翻查）。
- **D3 P7 拆大文件：暂缓**，排配件规格验收+规则中心设计之后（另一 AI 在动 kp 域，拆 kp_repo=撞车）。
- **D4 同名重复料合并：等规格补完后 Tier A 判据 dry_run 出报告交用户拍板**（价格同簇<1.3并/分散留，08-05 已验证判据）。
- **D5 兆芯→Polaris（CRE id=27）保留**（库内实证+只摆桌不落槽）。
- 结果集内二次过滤=**决定不做**（触发条件=库>2K件或翻页>2页再立项）。

## 09-12 深夜三段收口（A→C→B，用户批准顺序执行）

- **A 段（commit 3e1c6b4）**：指令唯一出处=左栏 manual_rules 单一家——节点层 prose 全清、node_mission 退役、description/goal/final_contract 从节点默认+流125 node_configs 清除；宪法测试 PROSE_MARKERS 检查面扩到 skill_node_plugins+selection_engine；zhaoxin e2e 231.9s/5轮/repeat=0。
- **C 段 S4 平台推导（commit 782bb0e）**：CRE 规则「平台：CPU 兆芯/KH→Polaris」（id=27，seed_missing_defaults 自动流库）；`registration_rule_context`（登记表→ctx）+ `catalog_derivations_for_registration`（空缺槽首命中）+ `_FillNode.prepare` 摆桌（事实行「推导值=…（推断值）」，引擎不发卡）；落槽仍走 fill/ask_user+前提闸门。e2e 227.9s/5轮/repeat=0，platform_type 卡带「Polaris（推荐）」。**AMD→Orion/Intel/海光 无目录证据未写规则，待用户拍板**。
- **B 段检索三件收口**：B1 rerank 评估后撤（用户裁定：排序病灶根因=库数据质量——同名重复行+规格缺口，去重/补规格才是修法；bge-reranker-base 1GB 已下载到 %TEMP%/fastembed_cache 留着可删；HF 直连被墙、镜像下载须 `HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`，Xet 协议走镜像 401）；B2 已由 P1 满足（向量 Postgres 持久化+content_hash 增量，实测 ensure 二次 reindexed=0）；B3 维持不做（触发>5K 件或重建>5s）。

## 架构（核验有效）

- 编排壳 `skill_turn_engine.py`（`run_skill_agent_turn`→`_SkillTurnRuntime`）+ 节点插件插座（DefaultNodePlugin + _Fill/_Model/_Kp/_Compose）；6 节点链 input→agent_fill→model_reason→kp_reason→compose→output；步进闸门 `step_gate_verdict`(advance/pause/deliver) + final_gate 终检。
- **原生 function calling**：文本式 ReAct 通道已从 skill 链路删除（禁回归）。`llm_client.py` 有 `supports_native_tools` 能力探测 + auto/native 通道 + `_is_native_tools_unsupported` 降级。`agent_react.py` 仍存在但只服务 AI 同事链路。
- **9 个模型工具**：fill_requirement / choose_model / query_parts / inspect_parts(part|row|category|grep) / select_parts / ask_user / catalog_search / search_cases / query_data。suggest_parts 已于 09-12 退役。（10-11 起注册表 11 项：+colleague_memory、+opportunity_stats；**query_parts 升双模式**——流程外日常浏览只读检索 limit≤10、rows 拒绝、mode=browse，价格仍 price_ok 门控，见 [[query-data-primitive]]）
- **检索三通道分层**（Agentic Search 对齐）：query_parts=找料（category+keywords+required_specs AND 过滤+offset 翻页+response_format）/ inspect_parts(category,grep)=导航 / inspect_parts(part,row)=看全。
- **去检索台账**：kp_search_index 接地台账已删；select_parts 落料按「类目+料号名」回库核对。part_id 是自增行号、不是业务 PN。
- **ext 影子存储退役**（09-12）：AI 流直读直写真实表 `opportunities.opportunity_requirements`（draft/current 版本），write_mode ∈ preview/draft/none。
- **行身份**：origin（reg:<类目>#n / cfg:<类目>#n）铸造 row_id，描述改写不换身份；09-12 归属收口（行只由属主产生）。一类多行完全合法；引擎明确**不做**文本相似度归并。
- P0–P6 施工轮次全部 ✅（09-11 定档收敍）；P7（拆聚合层大文件）可选待批。606 tests passed。

## 实测基线（09-11 P4 复测，权威）

| 场景 | 轮次 | 墙钟 | 配件行/组装行 |
|---|---|---|---|
| 兆芯详细 | 3 | 171s | 8/17 |
| B200 库内无料 | 7 | 426s | 2(1 waived)/12 |
| AMD 模糊 | 5 | 440s | 1/10（LLM 抖动） |

回放 43 真实线程：重复 row_id/origin=0、同义重复行=0。单轮 50~200s，根因 reasoning 模型深思考，不在编排。

**我 09-12 复跑 e2e（反问开·全旅程，scripts/e2e_skill.py 兆芯场景）：finished / 4 轮 330s / 8 配件行 17 组装行 / 0 重复卡行 / 3 张缺口卡全 brain_ask 可恢复（platform_type→server_type→RAID 卡行卡）。** 三点关键观察：①「4 个千兆+2 个万兆」口语词缺口被大脑自愈——零召回提示引导翻译后锁定 1G Intel I350 4 口 + 10G 双口含光模块，且**主动向用户澄清「张数 vs 口数」歧义**、终轮收敛到口数语义（×1+×1）；②推断槽位（platform_type/server_type）弹确认卡而非静默代填，符合 [[inferred-slots-must-confirm]]；③RAID 行卡 3 个真实候选+「保持原需求留白」弃权项、行绑定 row_id，选超级电容变体（超融合建议）。结论：管道今日可用，词法检索弱是软缺口（大脑绕过但多花轮次/时间），增强收益在提速与确定性，不在救命。

## 已知未修（§14 现存开口）

1. ~~grep_parts 命中后不能直接锁定~~ → **已关闭（09-12 深夜复核）**：§24 落料改按「类目+料号名」回库核对（lookup_parts_by_name），grep 结果带料号名可直接 select_parts，拒绝档已不存在；文档 §14/§20 已划。
2. ~~结果集内二次过滤缺~~ → **09-13 拍板不做**（库 288 件打库<1s；触发=库>2K 件或翻页>2 页再立项）。
3. 单轮推理耗时高（模型侧，延迟大头在思考不在 prompt 长度）。
4. ~~残留①语义边界~~ → **09-13 D1 拍板收口**：左栏规则 13 加「行归属纪律」（见文首 09-13 节），引擎层维持不归并。
5. **kp prompt 实测（09-12 深夜，rules.llm_trace agent_round 197 调用）**：avg 14.9k / max 38k prompt_chars——「14.9k 候选池」前提已证伪（§24 后池不在 prompt，AI 按需拉）；静态块精瘦（manual_rules 3596+steps 1219+slots 825+rows_all 1775≈7.4k 且逐字节稳定吃 KV 缓存）；大头=步内工具结果累积，已有 20k 上限+最老压缩（②c）。09-13 拍板 20k 上限不动。

## 我 09-12 数据层实测（data_tools 直测）→ 病灶当日已修（P0/P1）

part_query 14 例 10 中的四个病灶（中文口语零召回/智铠100→H100 误报/media 丢失/检索面窄）**已于 09-12 P0+P1 修复**，见下节。CPU 无核显字段仍是数据缺口，检索修不了。

## 检索增强已落地（09-12 P0 词法 + P1 混合，用户批准后当日完工）

- **P0 词法** `part_lexicon.py`（纯函数）：blob=name+brand+spec值+简介；DB 别名表 `kp.kp_search_aliases`（权威源，startup 空表种子 11 条，API `/api/kp/search-aliases`）；加权分级（原始中文段6>3gram5>2gram3+长词吸收子词，滑窗伪词降权）；判别轴互斥 {sata,nvme,sas,u.2}/{ssd,hdd}/{ddr3-5} 料沉默不过滤。
- **P1 混合** `part_search.py hybrid_search` + `part_search_index.py`：词法+语义（本地 fastembed bge-small-zh-v1.5 512 维，`kp.kp_part_search_index`，content_hash 增量、COUNT/MAX 对账新鲜度、料增改首查自动重建 288 件~28s）→ RRF(k=60)，**每条候选带 match 溯源**（lexical/semantic:0.xx）；语义候选照样过规格过滤+判别轴+**容量±1%守卫**（防向量压过硬信号：2T固态/141G 显存两实测病灶）；降级链=fastembed 缺席→纯词法（行为=P0），永不挂死。`_get_model` 默认 HF_HUB_OFFLINE=1 本地秒载（模型缓存手动放好：%TEMP%/fastembed_cache，HF 被墙断网时会挂网络重试几分钟才降级——重下模型须清该变量）。
- **接线**：query_parts 两模式（keywords/rows 批量）内部切 hybrid，工具契约不变；part_query/part_recall 保留纯词法给 assistant 直连方。
- **实测**：13 口径电池（scripts/hybrid_battery.py）混合 13/13 vs 词法 11/13；「训练加速卡」词法零→语义补位；单测 9+15 新增、全量回归 623 绿。库外近邻（HBM3e 141G→L20）按 [[requirement-gap-match-grading]] 定调回近邻+溯源交 AI 分级，不说「无料」也不拦截。
- 细节权威源：`docs/需求分析/02_工具与调研/kp选型-工具设计-搜料与选定.md` 文末「检索引擎落地」节。
- P2（rerank/规模/SQLite 向量）09-12 深夜收口：B1 撤、B2 已满足、B3 维持不做（见文首三段收口）。
- **配件库规格补全进行中（另一 AI 并行）**：enrich_kp_parts.py 等在工作区补 kp.kp_parts specs；完成后待验收：hybrid_battery 13 口径 + zhaoxin e2e（对比 227.9s/5轮/4卡基线，看同名行选料卡是否减少）；语义索引 content_hash 增量会自动重建无需手动。同名重复料（LSI 9361 三胞胎等）规格补全不消重，合并须用户拍板。

## e2e 复测入口

```bash
cd /d/CPQ_Platform_V1/backend && .venv/Scripts/python.exe -X utf8 scripts/e2e_skill.py --scenario scripts/e2e_scenario_zhaoxin.json
```
真实 HTTP+WS+LLM+库；登录凭据见 [[login-credentials-location]]；场景含「4个千兆，2个万兆」直接考口语词。单场景 3-7 轮×50-200s。注意：后端须跑新代码（launch.json 无 --reload，改代码后要重启；uvicorn 有 multiprocessing 子进程继承 8000 套接字，杀父进程后子进程仍活着，要找 `spawn_main` 的 python 一并杀）。
