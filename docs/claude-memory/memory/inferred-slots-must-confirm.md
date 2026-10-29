---
name: inferred-slots-must-confirm
description: "2026-09-06定调:AI推断槽位值必须弹确认卡+2026-09-13豁免条款:客户明示全权委托(一切你定/完全按推荐)时推断不逐项问,折进整体落定卡一次确认"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 73d41dbd-6e82-4e59-afee-65666db128df
  modified: 2026-09-12T20:08:05.772Z
---

用户定调（2026-09-06）：**凡是系统推断出来的（客户没明说的）槽位值，必须让客户确认**，不能静默登记。起因：真实会话里大脑把 server_type 推断成"通用计算服务器"直接落表，用户没点头。

**Why:** 推断值直接喂下游语义（机型候选过滤/平台规则），错了会整链跑偏；客户明说的项不用再问（烦），推断的项必须问（准）。

**豁免条款（2026-09-13 用户定调）：客户一开始明示全权委托（「一切你定/完全系统推荐/你看着配」）时，推断值不再逐项弹卡**——用户原话「不然系统一点智能性都没有了」。正解=推断照填（标 inferred）+ 类型/平台写进整体落定卡 desc，点「全部按推荐落定」一并确认+锁定：授权留痕不断（看得见、点过头才落槽），只是从逐字段确认合并为一次确认。委托识别归理解通道（agent_fill），不许 regex。

**How to apply:** 机制已落地（backend）：
- `skill_phases.inferred_confirm_gaps(ext, corpus)`：已填槽位值（标量字符串）去空白后在累计客户原话语料里做包含比对，找不到且 `ext.confirmed_slots[slot]` 未钉住当前值 → 产出 `reason_code="inferred_confirm"` 缺口（带 current=推断值，选项=目录词表含当前值），**排在缺失缺口之前**，随 S1 多卡同轮弹出。
- `skill_chat` 点选/打字落槽时写 `ext.setdefault("confirmed_slots", {})[slot] = value`（值被大脑改写即失效重新求证）。
- purchase_qty（引擎白盒默认）与 server_model（机型确认环节）排除；结构化值（list/dict）走部件表呈现不弹卡。
- 纯 LLM 口头推断（大脑直接说出来）不受此管——只管落了表的推断值。

**缺口逐条问（2026-09-06 用户定调，弃 S1 多卡同轮）**：用户明确 Claude Code 式一轮一问——「先选一个，选完再弹出下一个」；同轮多卡的观感=点一张兄弟卡齐塌、几秒后未答卡又重发=顺序错乱。实现：skill_chat gaps 循环 `gaps[:1]` 只发第一张卡（inferred_confirm 排最前），答完引擎恢复→下一缺口重新收敛再单发（resume 重收敛机制已被用户实跑落库数据证实）。last_card 只留可见卡选项，点击快速路径与屏幕一致。前端回合塌行语义保留作防御。

**多卡同轮塌行语义（2026-09-06 修，实机三连验证）**：S1 多卡同轮时，旧版把「本卡之后出现新选项卡」也当已答 → 第二张卡一落列第一张秒塌「已处理」（用户怒斥）。正解=回合粒度：卡已答 iff 之后出现**用户消息**（AssistantPanel/OfficeColleagueChatPanel 的 optionAnswered，两处同构）；未答兄弟卡回合收口塌「已收起」非「已处理」；新一轮对剩余缺口重发新卡（AssistantMessageItem collapsedAnswer 兜底标签）。改一处语义必须同步另一处拷贝。关联 [[skill-takeover-diagnosis]] [[skill-tree-trunk-architecture]]
