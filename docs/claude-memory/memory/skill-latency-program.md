---
name: skill-latency-program
description: 09-12根修四件套落地+复测：471s→368.6s/假等待180s已除/撞顶循环0命中；含 _cap_tool_context 死循环 postmortem 与 e2e 隔离跑法
metadata: 
  node_type: memory
  type: project
  originSessionId: 73d41dbd-6e82-4e59-afee-65666db128df
  modified: 2026-09-12T16:14:04.188Z
---

需求分析 skill 延迟优化程序已落地（用户 09-05 批准）。

**Why:** E2E 8 分钟（130+77+259s）做一次简单需求登记+选型，用户要求按 Claude Code/ChatGPT 交互形态重造而非调参。

**How to apply:** 碰 skill 延迟/轮次/trace 时先看本记录的实测数字与根因，别重新归因。

落地内容：
- S1 缺口一次问全：skill_phases.target_layer_gaps（≤4）+ skill_plan_runtime._pause_with_gaps + skill_chat 弹卡区循环发多卡（narration 只随第一张卡落库）
- S2 打字答案落槽：pending 卡 + 短文本(≤30字符无换行) 唯一命中选项 → 视同点选
- S3 确认+引问合一：make_fill_brain user_msg 改双段指令；fill_narration 存在且全 target_incomplete 时跳过 gap-ask LLM（数据兜底问句）
- S5 任务大脑 effort=low 默认（task_reasoning_effort，profile 可覆盖）
- O0 llm_trace 逐调用：node_type ∈ skill_agent_fill/skill_model_reason/skill_kp_reason/skill_propose/skill_gap_ask/skill_final + skill_chat 总计行；contextvar set_trace_ctx
- 护栏：run_stream_chat_loop 新增 llm_max_tokens 透传 stream_agent_chat；三个 make_*_brain 传 8000（拦单轮生成跑飞，截断标记走既有压缩重试路）
- 第二批（同日批准，对齐 Claude Code「少说多做」，不砍输入智能）：
  - L3 system 静态化：登记表/已锁行/候选池等每轮变化的数据从三大脑 system 挪到 run_stream_chat_loop 新参 context_block（拼进尾部 user 消息），system 逐字节稳定保上游 KV 缓存前缀
  - L1 思考看门狗：_stream_round 思考流超 llm_thinking_budget(默认2500字符) 且正文未开始 → 断流置 truncated 走既有压缩重试路（拦代理忽略 effort 的随机深思考轮）
  - L2 旁白预算：三大脑指令各加「每段说明≤3句，比对过程不汇报」

实测（兆芯场景，rules.llm_trace）：
- 第一批后：点击路 T2 71.9s（护栏拦跑飞）；打字路 T2 170s（两个贴 cap 轮）
- 第二批后：**点击路 T2 44.0s；打字路 T2 69.2s 且 2 轮跑完全旅程**（锁定 ZS22V2-P+配件5项+整机组装+交接产物）；kp 轮全部 3-13s，无跑飞
- E2E 每轮 T1 的 ~40s 前置 = thread resolve 清理上个在途预览线程 + 热重载冷启动，非稳态成本
- 打字路 T2 旁白偏简（kp 锁定结果没在聊天流展开，走 final report）——deepseek 行为方差，数据锁定无缺失

根因（关键，**2026-09-12 修正**）：cloudprime 代理对 **reasoning_effort=low 的忽略是「带 tools 的调用」专属**——无 tools 的纯对话 low 生效（思考 775→0 字，探针实测）；带 tools 的流式调用思考照跑 1200-5400+ 字（e2e 逐轮 trace 实测）。旧说法「~50% 忽略」实为「tools 调用全忽略」。根治需基础设施：代理修复或任务大脑换非 reasoning 模型。

**2026-09-12 逐轮 trace 实测（D 落地后）**：
- 全旅程 e2e 5 回合 wall 471s 中 **~180s 是 e2e 驱动假等待**：gaps 回合后端只广播裸 `done`（colleague_turn_runners gaps 分支），驱动只认 analysis_finished/pipeline_done → 每个反问回合白等 45s 静默超时。反问回合真实引擎耗时 13-22s。**修法：gaps 路径补广播 pipeline_done（裸 done 必须保留，前端靠它清 streamingText）**。之前的 E2E 轮次对比全部被此噪音污染。
- 真实大头 = 最终回合 229s：20 轮 LLM≈191s，其中 **~128s 是 thinking 撞顶循环**（budget=12000 字，撞顶轮思考恰好 12001/12007/12003 字→掐断→「压缩重试」→再撞顶→bail→步级 fresh 重试，kp_reason 整步尝试 ~3 次，上下文 9.7K→38K 字）。撞顶掐断+重试是净损失；候选修法：撞顶放行到完成 / 撞顶一次后注入硬指令直接作答。
- DeepSeek 前缀缓存穿透 relay 生效（同前缀二连打 warm 91% 命中，prompt_cache_hit_tokens>0）——重复 system/规则的传输成本已被缓存打折。
- llm_trace 新列 thinking_chars/prompt_tokens/completion_tokens/cache_hit_tokens + agent_round 逐轮记录（duration/包字数/思考字数/工具名）；relay 对带 tools 请求不回 usage（字符数代理）。
- 坑：agent_react 的 _record_round 在单测里也写真库 rules.llm_trace（tests 用 mock LLM 仍触发），测试会污染 trace 数据，待修。

**2026-09-12 晚根修四件套已落地并复测通过（用户批准 1+2abc+4）**：
- ①统一回合终态：gaps/done/error/chat 四分支末尾都广播 `turn_finished`（新事件，不复用 pipeline_done——前端该分支会把 paused 改写成 done）；e2e 驱动 break 但不置 finished。反问回合墙钟 57-66s→13-24s。
- ②a 思考护栏改硬顶×3（`_THINKING_HARD_CEILING_MULT=3`）：软预算不再掐断，思考放行到完成；复测 **ceiling_hits=0**（基线 20:53-20:55 三分钟 thinking 钉死 12001/12007/12003 烧 165s）。深思考轮 45.8s/31K 字能出真产出（重复料号排查），不再双倍付费零产出。
- ②b 检索结论持久化：run_brain_attempts 新参 findings_out（attempt>0 注入「此前已完成的检索/工具结果」）+ skill_turn_engine `self.mem["step_findings"]` 跨步保留（done 弹出、留最近 2 个未完步）——检索结果像登记表一样不随失败尝试蒸发（交接靠表铁律的落地）。
- ②c 步内工具上下文总量上限 20000 字（`_cap_tool_context` 压最老工具消息，上下文 ≤33K vs 基线 38K+）。
- ④tests/conftest.py autouse stub record_llm_trace——单测不再污染真库 trace。
- **复测（隔离实例全旅程）**：wall **471s→368.6s**，4 回合 finished，repeat_cards=0，kp_rows=8/组装 17 行，配件全部锁库内真实料号，还多干了一件基线没干的活（同名重复 480G SSD 弹确认卡+复锁）。引擎轮 35 轮 344s——比基线 255s 多是因为真产出更多，不是浪费。
- ⚠️ **postmortem：②c 首版死循环卡死整个事件循环**（py-spy 抓栈 `_cap_tool_context` active+gil）：压缩后长度 400+12字标记=412 > 400 门槛 → 同一条消息被反复"压缩"到同样长度、总量永不降 → while True 永不退。机型+配件阶段工具消息最多必触发，表象=e2e 在该阶段反复"被重启杀死"（ping 超时/清理超时）。修法=压缩后长度(≈312)必须严格低于 victim 门槛(400)，附回归测试 test_cap_tool_context_terminates_and_shrinks（624 全绿）。教训：**同步 while 压缩循环要证不变量"压缩产物不可再被选中"，且 e2e 同一阶段反复中断先怀疑服务端挂死（py-spy dump），别只盯着 reload**。
- **e2e 隔离跑法（并发干扰免疫）**：`.venv/Scripts/python.exe -X utf8 -m uvicorn app.main:app --port 8001`（**不带 --reload**）+ `E2E_BASE=http://127.0.0.1:8001` 环境变量跑 scripts/e2e_skill.py——8000 主实例的 reload（自己/他人改码触发）杀不到隔离实例。e2e_skill.py 的 BASE/WS URL 已支持 E2E_BASE。

09-12 深夜进展（A/C 段落地后）：S4 平台推导已落地（CRE 规则 id=27+prepare 摆桌，见 [[skill-current-state-2026-09-12]]）；③指令唯一出处定调=左栏（节点抽屉不放指令，node_mission 退役，commit 3e1c6b4）；P2 检索三件收口：B1 rerank 评估后**撤**（用户裁定：同名重复行/规格缺口是数据质量活，精排是 5K+ 件规模的事；接线已删、bge-reranker-base 模型缓存留 %TEMP% 可删）、B2 向量磁盘缓存**已由 P1 满足**（实测 ensure 二次 reindexed=0/load_vectors 0.15s，Postgres 持久化+content_hash 增量）、B3 维持不做。zhaoxin e2e 新基线：A 段 231.9s / C 段 227.9s（5 轮 finished、repeat=0、platform 卡带「Polaris 推荐」）。

未做（用户排期）：配件库规格补全后的检索验收（另一 AI 在补 spec 数据，完成后跑 hybrid_battery+e2e 对比 227.9s 基线）；同名重复料合并（须用户拍板口径）。~~AMD→Orion/Intel/海光 平台映射三条规则（待业务确认）~~ → **用户 09-12 定调：规则中心建好前不写规则、允许 AI 幻觉（插头插座设计），S4 插座已就位（catalog_derivations_for_registration+prepare 摆桌），规则中心做好后从插座接入**；已写的兆芯→Polaris（id=27）是库内实证（KH50000 只适配 Polaris）保留，且只摆桌不落槽、终走确认卡。kp prompt 瘦身挂账已销：实测池不在 prompt、大头=20k 工具上下文上限（见 [[skill-current-state-2026-09-12]] 已知未修⑤）。

关联 [[skill-takeover-diagnosis]] [[llm-provider-relay]] [[agent-architecture-decision]]
