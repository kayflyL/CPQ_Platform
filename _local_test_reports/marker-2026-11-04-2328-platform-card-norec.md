# 标记 2026-11-04 23:28 · 平台确认卡无推荐 + 旁白/卡头双问

线程：`7115349017414b94962e8992d97a9af2`（配置团队，23:28 暂停）
用户说「国产服务器」→ 暂停在 agent_fill，出平台确认卡。

## 标记 1：卡片没有推荐了（Polaris 不置顶、无「推荐」标）

**根因（DB 现场实锤）**：`ext = {"server_type": "通用计算服务器"}`——大脑这轮把
「国产」判成整机级歧义（旁白问「是指纯国产 CPU 的 Polaris 吗？」）**没有登记
platform_type**，于是走的是 `stuck_gaps` 缺字段出路卡，而不是我上一轮修过的
`system_gaps → _premise_confirm_gap` 求证卡。同一张卡脸、两条代码路径，上轮只修了
求证卡那条；`stuck_gaps` 是裸目录序、无推荐逻辑（skill_node_plugins.py 原_lines 372-374）。

**深层事实**：规则库里根本没有「整机国产→Polaris」这条归置规则——只有兆芯/KH→Polaris、
AMD/EPYC/霄龙→Orion、Intel/至强→Intel。大脑靠目录常识犹豫、机制层对「国产」全盲。

## 标记 2：旁白问了问题，卡头又问一遍

卡头=大脑 ask_user 的 `question` 参数原样展示；旁白又复述同一问。工具契约此前未声明
「question 即卡头、旁白别复述」。

## 处理

1. **机制·双路径合一**：`stuck_gaps` 缺字段卡改走 `_premise_confirm_gap` 同一装饰路径
   （候选+推荐+影子标注），不再各自手搓选项数组。
2. **机制·确定性推荐兜底**：新增 `requirement_knowledge.dict_signal_seed(原文, slot)` ——
   归置规则信号词扫 `engine.requirement_text`（客户原话全文，引擎本就携带），唯一命中→
   推荐置顶+标注「按归置规则信号命中（推断，可改）」；多值命中=歧义→None 不猜。
   已接线 engine_wiring.MODULE_ATTRS。
3. **业务·补规则**：新增规则 38「平台：整机国产/信创/自主可控 → Polaris」，信号词
   国产/信创/自主可控，依据=业务确认（2026-11-04 测试口径），已置 active（编辑器可改可删）。
4. **契约·ask_user**：description 声明「question 作为卡头完整展示，旁白不再复述」。

## 离线验证（真实 DB）

- `dict_signal_seed('我需要一台国产服务器…')` → Polaris；'信创' → Polaris；
  '国产+AMD' → None（歧义不猜）；无关需求 → None。
- `stuck_gaps`（ext 只有 server_type）→ 卡：Polaris 置顶+recommended+规则命中 desc，Orion 次之。
- 求证卡（已登记 Polaris）→ 置顶+recommended 保持。
- 后端重启无新告警（capability_spec 那条为历史遗留）。
