---
name: no-git-restore-concurrent-sessions
description: 并行会话同时改这个仓库时禁用 git restore/checkout 回退自己的改动，只用 Edit 精确撤销；restore 会连带抹掉别人未提交的工作
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 15ad3f25-838d-415a-a0e5-4c7687166020
  modified: 2026-09-19T08:28:42.801Z
---

这个仓库常有**并行会话同时改代码**（另一台机器/另一个 chat 的 dev server 同时在跑、批量未提交改动是常态）。需要撤回/回退**我自己**的改动时，**禁止 `git restore` / `git checkout --`**，一律用 Edit 工具把我写的内容精确删掉。

**Why:** 2026-09-19 门户美化撤回时踩坑：我用 `git diff` 核对过 hunk 都是我的才 restore，但 Portal.vue 里别人一行未提交改动（`.portal` 高度 100%→`calc(100% - var(--cpq-header-clearance))`）恰好在我的编辑范围内被原样保留——diff 里根本不显示，restore 后被静默抹掉，用户专门来提醒「其他板块也在同步改动，你不要把人家的也给撤回了」。

**How to apply:**
1. 回退自己的改动 = 逐条 Edit 反做（自己写了什么就删什么），不用任何会整文件回退的 git 命令。
2. 如果确实必须整文件回退：先确认该文件没有别人的未提交改动（对照会话开始时的 git status + 完整读过的工作副本），且用户明确同意。
3. 隐蔽坑：自己的编辑若"碰巧保留"了别人的未提交内容，diff 检查会漏检——别信「diff 里只有我的改动」就安全。
4. 同理：git status 里大量脏文件是别人的在途工作，不是垃圾，别清理别提交别覆盖。
