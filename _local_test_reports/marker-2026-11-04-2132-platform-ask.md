# 标记 2026-11-04 21:32 · 需求分析工作流 · Skill Studio 试运行

- thread: `d888c79058204220a42687230cf8404c`（opportunity `ai-ebd93bcc38f44ef28f928b3b`）
- 入口: AI 办公室管理 → 工作流 → 需求分析 · 试运行（预览 5174 / 后端 8000）

## 用户标记

1. 说「我需要一台国产服务器」后仍被反问平台类型（Orion/Polaris），疑似节点抽屉规则层断了
2. 思考完成后全屏消息消失一下才弹出内容（闪空 ~3s）

## 现场证据（tape + DB 复核）

### 问题 1：反问平台
- 消息史:21:31:41 用户「我需要一台国产服务器」→ 21:32:31 回合结束,text + 合批卡(server_type 通用/AI + platform_type Orion/Polaris)
- **登记 ext = {} 全空**——大脑旁白说「依据国产兆芯系列对应 Polaris、国产平台已记录」,但一个字段都没写(连需求原文都没有);steps_done=[]
- 卡 options 无 recommended / rule_match 标注(影子校验没命中)
- 规则库:rule 27 active「CPU 兆芯/KH → Polaris」,信号键=kp.CPU.spec.text(CPU 型号维度,不含「国产」);rule 28 AMD→Orion;29 Intel→Intel
- 结论:**规则层没断**。断的是「大脑理解对了 → 没申报」:国产→Polaris 是大脑自身知识推理(规则只认 CPU 信号,登记里也没 CPU 信号可用),它推对了、话说了,但工具契约没让它在同一轮把推断值申报进登记表;字段空 → stuck_gaps 出原始目录候选卡(无推荐无规则标注),用户被反问
- 注:设计定调「推断必确认」+「影子校验永不代填」未被违反——缺的是大脑「先申报再问」的契约环节

### 问题 2:闪空
- tape 时序:pipeline_waiting 148.78s → done(文本消息) 152.00s → chat_progress(卡片) 152.04s;中间 ~3.2s 空白
- 根因:前端 pipeline_waiting/pipeline_paused 处理器当场清 `streamingText`,旁白气泡/全屏层立刻消失,消息 3.2s 后才到
- 修复:暂停不清旁白,由 done(推消息+清流式,同一拍原子交接)或 adoptTurnEnd(watchdog 兜底)清

### 附带发现
- tape 中每条事件都出现两次——该线程疑似双 WS 连接(试运行面板 + 浮动助手同订一处?),未确认是否有害
