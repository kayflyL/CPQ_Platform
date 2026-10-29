---
name: cc-switch-502-root-causes
description: cc-switch 本地代理(127.0.0.1:15721) 瞬断 502 SendRequest 的三类根因+解法（GitHub 调研结论），会话再断先看这条
metadata: 
  node_type: memory
  type: reference
  originSessionId: cc77fad8-e822-48e6-851f-c09e46f5e31d
  modified: 2026-08-16T11:05:19.556Z
---

# cc-switch 瞬断 502 根因与解法（2026-08-16 调研+实测）

链路：Claude-3p Electron 客户端 → cc-switch 本地代理 `127.0.0.1:15721`（v3.19.2）→ cloudprime（`http://api.cloudprime.com.cn:5567`）。报错样式：`API Error: 502 请求转发失败: 上游请求失败: client error (SendRequest)`。

## ★ 本机实测根因（2026-08-16 日志实锤，优先看这个）

**cloudprime 上游限流（429）+ 高压时直接掐连接**。cc-switch 日志 `~/.cc-switch/logs/cc-switch.log` 证据：
- 断点时刻：连接错误每38秒一次连挂5次 → 紧接 25+ 条 `HTTP 429 [1302][Rate limit reached]`
- 近5天 429 计数：80/150/405/22/206 —— 慢性贴限，SendRequest 与 429 正相关（限流压力大时 cloudprime 掐连接不回 429）
- Claude Code 对该错误重试5次全挂 → 整轮失败 → 会话断

**已排除**：v2rayN 回环劫持（ProxyOverride 已含 localhost;127.*）；cc-switch 版本（已最新）；代理环境变量（干净）。

**解法（供应商额度动不了时的客户端措施，2026-08-16 已部分落地）**：
- 实测额度线：基线 8-13 请求/分没事，**冲到 38-45/分就连环 429**（每分钟峰值统计与 429 高发时段完全重合）；失败瞬间客户端还会 1 秒内齐射 ~25 个重试请求（stampede 正反馈）
- 已落地：`~/.claude/settings.json` 加 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`（砍后台非必要调用）+ `API_TIMEOUT_MS=600000`（防长思考被客户端超时掐）
- cc-switch 侧（UI 操作）：`auto_failover_enabled` 目前 0，且 claude/claude-desktop **只有 cloudprime 一个活供应商、failover 没备胎**（codex 已配好「公司+公司 copy」可参照）；加个备用供应商（如 SiliconFlow/GLM 官方免费档）再开 failover 才是结构性兜底
- cc-switch 无内置限流旋钮（proxy_config 全列已核对：只有 retries/熔断/超时）；多 Key 轮询是 [#4957](https://github.com/farion1231/cc-switch/issues/4957) 未实现
- 行为约束（对我自己）：**避免并行 subagent 大扇出**（一次 1-2 个、顺序跑），重任务别多会话同时开——所有请求共享同一 RPM 池
- 兜底：断了发「继续」接上即可

## GitHub 同类问题参考（farion1231/cc-switch，搜「502」78 issue）

三类通用根因，本机实测均非主因但留作参考：

1. **系统代理劫持流量**（最常见）
   - [#3989](https://github.com/farion1231/cc-switch/issues/3989)：同端口 15721 同款报错，已验证解法 = **Clash 配置把 `localhost`/`127.0.0.1` 强制直连(DIRECT)**
   - [#4789](https://github.com/farion1231/cc-switch/issues/4789)：Win11 + Clash Verge 系统代理模式必现，切 **TUN 模式或关系统代理**立即恢复
   - [#4642](https://github.com/farion1231/cc-switch/issues/4642)：cc-switch 会缓存系统代理设置且不动态刷新（macOS 报的，Windows 同理注意）

2. **推理模型静默思考窗口被掐**（与本项目推理模型高度相关）
   - [#5877](https://github.com/farion1231/cc-switch/issues/5877)：上游偶发掐 SSE(~0.17%)，代理层零重试整轮失败；且 cc-switch 自带 **120s passthrough 空闲超时**——推理模型（deepseek-v4-pro/step-3.7-flash）提交后静默思考数分钟恰落高发窗口
   - 修复 PR [#5878](https://github.com/farion1231/cc-switch/pull/5878)：移植 Codex CLI stream_max_retries=5 到代理层，**截至 2026-08-16 未合并**（最新版 v3.19.2, 2026-08-06），合并后升级即根治

3. **特定工具载荷触发损坏 passthrough 路径**
   - [#5399](https://github.com/farion1231/cc-switch/issues/5395)：报错逐字一致；请求含官方 **Grep 工具 offset 描述**（shell 管道片段）或 **mcp__Claude_Browser__preview_\*** 工具 → 确定性推到坏 passthrough。本项目两者都常驻（Grep 自带 + 浏览器 MCP）。issue 仍 open

## 排查/处理顺序

1. 有代理软件在跑 → 127.0.0.1/localhost 强制直连或切 TUN（零成本，#3989 实锤）
2. cc-switch 升到最新（3.16.5 报的③可能已修）
3. Watch PR #5878 等合并升级（②根治）
4. 兜底：会话断 ≠ 丢上下文，transcript 落盘，重开发「继续」即接上

相关：[[llm-provider-relay]]、[[claude-3p-environment]]、[[llm-reasoning-model-pitfall]]
