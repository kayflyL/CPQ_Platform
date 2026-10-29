---
name: claude-3p-environment
description: "本环境是 Claude-3p 第三方客户端(Electron 套壳 + 魔改 Claude Code + GLM 代理),anthropic-skills 装在 AppData 会话目录而非 ~/.claude/skills/"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 657bbc21-3e34-47ea-a5e8-c3bec99880fb
  modified: 2026-07-25T12:31:52.994Z
---

当前运行环境**不是官方 Claude Code CLI**,而是 **Claude-3p** 第三方客户端:

- Electron 套壳(特征目录:`Cache` / `Crashpad` / `GPUCache` / `DawnGraphiteCache`),内置魔改版 Claude Code(见 `AppData\Local\Claude-3p\` 下的 `claude-code` / `claude-code-vm` / `vm_bundles`)
- 走本地代理 `127.0.0.1:15721`,实际模型是 **GLM-5.2 套 Claude 兼容壳**(settings.json 里 `ANTHROPIC_DEFAULT_*_MODEL_NAME: glm-52`),非真 Anthropic API

## Skill 实际位置(非标准)

`anthropic-skills:*`(frontend-design / docx / pdf / pptx / xlsx / consolidate-memory / schedule / setup-cowork / pdf-reading 共 9 个,正是 Anthropic 官方开源那套)装在:

```
C:\Users\16891\AppData\Local\Claude-3p\local-agent-mode-sessions\
  skills-plugin\00000000-0000-4000-8000-000000000001\<session-uuid>\skills\<name>\
```

- 路径含 `<session-uuid>`,每次会话镜像一份到私有目录
- 结构是标准 Anthropic skill 格式(`SKILL.md` + `LICENSE.txt`),`Skill()` 能正常调起,内容正版完整

**Why:** `find ~/.claude` 找不到这些 skill,容易误判为「没装」或「代理注入的假条目」而建议用户重装。

**How to apply:**
- 怀疑 skill 没装 / 调不动时,先去上面那个 AppData 路径看真文件是否在,再下结论
- `Skill(anthropic-skills:frontend-design)` 等可正常调用,不必让用户装第二份(如 ui-ux-pro-max,会与项目 [[glass-console-system]] 打架)
- 想换官方 CLI 时,把这些目录复制(非剪切)到 `~/.claude/skills/` 即可被识别

## ~/.claude/skills/ 现状(2026-07-25 更正)

**此目录会被 Claude-3p 客户端实时加载,可装用户级新 skill。** 2026-07-25 装 `remotion-dev/skills`(11 个 skill,157 文件)到此目录后,客户端在下一次 system-reminder 里立刻列出 `remotion-create`/`remotion-markup`/`remotion-render` 等,Skill() 可正常调起。

此前「~/.claude/skills 不被读、装了没用」的论断**过时**,实际两个位置都能加载:
- `AppData\Local\Claude-3p\...\skills\` — 客户端预装的 anthropic-skills(9 个)
- `~/.claude/skills/` — 用户自装的全局 skill(如 remotion),跨项目/跨会话可用

**Why:** 之前因 graphify 移除后目录空了一阵,误判为「客户端不读这里」。
**How to apply:** 装 GitHub 上的新 skill 时,若 `npx skills add` 因 github.com 443 被墙失败,直接用 `api.github.com/git/trees` + `raw.githubusercontent.com`(raw 间歇超时,api 稳定且返回 base64 content)手动下载落到 `~/.claude/skills/{name}/`,客户端会自动识别。

## 相关

前端设计触发规则已写入项目根 `CLAUDE.md`(涉及前端新页面/视觉/组件样式时先 `Skill(anthropic-skills:frontend-design)`,但以项目 [[glass-console-system]] 为准)。
