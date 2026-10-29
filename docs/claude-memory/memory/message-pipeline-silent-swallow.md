---
name: message-pipeline-silent-swallow
description: "2026-08-28定位\"卡住不回话\"真因=消息管道静默吞消息（错误只走WS广播+应用日志零配置黑洞），修复三件套待用户批准"
metadata: 
  node_type: memory
  type: project
  originSessionId: 103415a3-4b46-42b1-a04c-db5d6194e356
  modified: 2026-09-13T12:25:36.766Z
---

2026-08-28 实测定案：「发消息后几分钟无回复」不是 LLM 慢（同配置裸调 1.4s）、不是 DB 锁（pg 3/100 连接无等待）、不是僵尸进程（py-spy 全 idle），而是**架构级静默吞消息**：回合任务无声结束，无回复/无错误消息/无日志/无超时兜底。

三个结构性缺陷：
1. 错误上报只走 WebSocket 广播（客户端未连接/刷新即蒸发），不落库；
2. main.py 零日志配置，全代码库几十处 logger.exception 写进黑洞，出错不留痕；
3. 每条消息串行穿 4 层遗留管道：office_memory → 空间意图 LLM 分类器（办公室头像走位功能串在所有聊天消息前，误判即把消息当移动指令吃掉；用户截图"浮出方案助手头像"即此系统动作）→ 分派规则 → 对话脑。

**Why:** 打地鼠式逐层排查无法收敛——任何一环静默失败都表现为"卡住"，且系统被设计成出错不留痕；这是可观测性架构缺失，不是单点 bug。

**How to apply:** 修复三件套已落地（2026-08-29 用户批准）：①空间意图已从聊天主路摘除；②错误必达终态（落库+日志）；③main.py basicConfig 接通日志。**头号根因=uvicorn --reload 重启窗口杀在途回合**——已根治：launch.json 去掉 --reload 改稳定模式（改代码不自动生效，需显式重启且只挑无测试时机、重启前告知用户）。另修：submit_registration 目录词表校验（防自由文本场景提交死循环）+react循环60s×2/low档。实测全链路68s走通（模糊输入→目录澄清→映射AI/加速类型→配件闸门）。

**relay 黑洞挂死（2026-09-06 晚，kp 配件阶段 3 次复现）**：kp 大脑若干轮 LLM 调用后整个回合任务静默挂死——无新 trace、无 DB 锁、主循环 idle 在 select（任务在等永不就绪的 I/O）、py-spy 看不到协程栈。特征=有连接、无数据、也不断开（疑 cloudprime relay 流式黑洞，keepalive 字节会让读超时不触发）。三层防线已立（不依赖找到黑洞根因）：①大脑回合 300s 硬上限 brain_with_cap（skill_plan_runtime，fill/kp/model 三处）；②整回合 900s 放弃式超时（skill_chat asyncio.wait+cancel 不等取消完成，弃任务转"重新继续分析"卡）——**内层 wait_for 的取消完成也可能被 httpx 黑洞清理拖住，必须用放弃式不能等**；③WS 广播 5s 有界（assistant_hub，半死连接不再拖死广播方）。数据瘦身同步：kp 池视图每行候选 6 条/specs 4 键/剔 currency（prompt 12-14K→8.8-11K），response_chars 恒 2501 之谜（输出疑似被思考预算压缩机截断→工具调用不完整→重试churn）未解。**教训：测试期间改后端文件=reload 杀在途回合，表现为同样静默（勿与黑洞混淆，对比 trace 停止时刻 vs 文件修改时刻）**。

**四个回合终定案（2026-09-06）**：「流程走完 AI 停三个点、方案卡不出」真因=**business_entity_ready 事件的 message 字段是纯字符串**（colleague_turn_service 只落库不广播，广播时塞 result_msg 字符串），前端 pushMessage 把裸字符串推进 messages 数组 → AssistantMessageItem 落进 am-bubble--live 兜底分支渲染永久 .am-typing 三点泡（无 colleague_role_key 头像回退「方案助手」——用户截图正是方案助手头像三点泡）。卡片分支 kind=business_artifact 永不可达，刷新才从历史加载出卡=「你硬刷新就好了」假象。修复：后端广播 repo.add_message 返回的完整落库对象（与 done 事件同口径）+ 前端 assistantChatWs 对旧格式字符串兜底组装。**教训：三点泡=messages 数组里有一条渲染不出内容的消息，先查数组被塞了什么，别先怀疑传输/后端/旧页签。之前「传输丢失」「旧页签」两次结论都错，靠落库 assistant_messages + llm_trace 对时间线才钉死。**

**全局卡「模型思考中」（2026-09-13 定案）**：done 落在 WS 重连空窗（vite proxy 疑似 ~2min 空闲断开，一个线程 15min 重连 7 次）→ 看门狗 resync 用「有未见消息」判终态，但卡片消息已 WS 先到本地 → 永远判不出结束 → 全局 waiting/running 卡死 → **切到哪个角色都显示同一颗「模型思考中」泡 + composer 全员禁言（后端日志零 POST 是铁证）**；硬删当前线程自救 → resync 404 死循环锁死。修复=服务端事实替代猜测：`_THREAD_TURN_ACTIVE`（排队不算在跑）+ messages 端点返回 `turn_active` + 两个 resync 改「未见消息 ∨ turn_active=false ∨ 404」判终态。**教训：①waiting/running 是全局单例，卡死=所有角色同时假死，别按单角色排查；②后端日志零 POST=请求根本没发出（composer 被 running 禁言），别再找"POST 去哪了"；③恢复判定必须用服务端事实（turn_active），客户端"有没有新消息"是猜测。**

**排查套路**：先查 opportunities.assistant_messages 有没有卡片消息（有=前端问题，没有=后端问题）+ rules.llm_trace 看 skill_chat totals 行是否 ok + 前端 window.__wsEvents 看事件到没到，三方对时间线。关联 [[skill-takeover-diagnosis]] [[agent-architecture-decision]]。
