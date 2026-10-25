# Claude 环境暂存（跨机器迁移用）

本目录是 Claude 开发环境（项目记忆 / 全局配置 / 技能）的随项目暂存区，2026-10-24 为换机迁移建立。
`docs/` 整目录在 `.gitignore` 里，这里的内容**只随项目文件夹拷贝走，不进 git/GitHub**。
⚠️ 记忆里含内网地址、数据库密码等敏感信息，整个项目文件夹不要外传。

## 内容与原始位置

| 文件 | 原始位置 | 用途 |
|---|---|---|
| `memory/` | `C:\<用户名>\.claude\projects\D--CPQ-Platform-V1\memory\` | 项目记忆（MEMORY.md 索引 + 158 条踩坑/定调） |
| `CLAUDE.global.md` | `C:\<用户名>\.claude\CLAUDE.md` | 全局规矩（CodeGraph 使用约定） |
| `settings.global.json` | `C:\<用户名>\.claude\settings.json` | 全局设置（权限白名单等） |
| `skills/` | `C:\<用户名>\.claude\skills\` | 24 个用户级技能 |

## 新机器还原

前提：项目放在 `D:\CPQ_Platform_V1`（**路径一致则记忆目录名不变，直接照抄**）。
若路径不同，记忆目录名 = 盘符与分隔符转成横杠，例如 `E:\dev\cpq` → `E--dev-cpq`，下述第一条命令的路径要相应改。

用户名换成新机器的实际用户名，在项目根目录执行：

```bash
mkdir -p ~/.claude/projects/D--CPQ-Platform-V1
cp -r docs/claude-memory/memory ~/.claude/projects/D--CPQ-Platform-V1/memory
cp docs/claude-memory/CLAUDE.global.md ~/.claude/CLAUDE.md
cp docs/claude-memory/settings.global.json ~/.claude/settings.json
cp -r docs/claude-memory/skills ~/.claude/skills
```

## 老机器反向同步（记忆有新增时刷新暂存）

```bash
rm -rf docs/claude-memory/memory
cp -r ~/.claude/projects/D--CPQ-Platform-V1/memory docs/claude-memory/memory
```
