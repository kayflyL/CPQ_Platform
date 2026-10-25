---
name: edit-long-payload-corruption
description: 长负载 Edit/Write 生成会掺杂质 token（跨会话复发）：拆小块+逐字拷贝+读回+构建验证
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 14c1c9bd-5e8c-43c0-aefe-24deb15b1f73
  modified: 2026-09-30T06:27:55.126Z
---

长内容生成不可靠：多个会话里，我在长 Write/大段 Edit 的 new_string/old_string 中掺入了不存在的 token（`ref(ref`、` inset`、`'狼u8154'`、`to: map string`、`remaining roles:`、路径大小写写错 `Platform_v1` 等），有的静默落盘。触发条件=单次负载 >30-40 行，尤其中英混排长行。

**Why:** 生成端缺陷不是环境问题；出杂质时我往往"感觉写对了"——不能信手感。⚠️09-29 复发升级：**小负载（~8 行）也连续两次中招**（路径打成 `CPQ_Plused_V1`/`CPQ_PLATFORM`、`id: shibai`、`ref(null) as any` 静默落盘），还犯过拿占位符当 old_string——"拆小步"不再免疫。⚠️09-30 再升级：**整文件 Write 也中招**—— OnlinePill.vue 连续 4 次：content 里掺整段"自我对话"文本且**自感成功落盘**（工具返回 success！）、file_path 漂移成垃圾路径（`Class OnlinePill.vue`/`CPQ_PreviewVerify_*`）并真创建了垃圾文件；伴随输出通道退化循环（同一句重复刷屏）。教训：**工具返回 success ≠ 内容干净**，新文件 Write 后必须 Read 回读；发现落盘污染立即换 Bash python/heredoc 通道重写（该通道当天 3 次全干净）；通道退化循环靠"只发工具调用+极短过渡文本"打断。

**How to apply:**
1. 大文件改写拆成 ≤30 行的小步（占位 marker `// __X__` + 逐段 Edit 替换），每步之间不必读回，但**整文件拼装完必须通读一遍 + 跑构建**。
2. Edit 的 old_string 一律从当轮 Grep/Read 输出**逐字复制**，禁止凭记忆重打（`100vw`→`100vh` 这类近亲错字 grep 抓不到语法、build 才报）。
3. Write 前核对目标路径大小写（Windows 不敏感，`Platform_v1` 会直接覆盖真文件）。
4. 改 CSS 规则时 old_string 只截到确认存在的行，别假设规则在哪结束——曾在规则中段插 `}` 把 `flex-direction` 甩出块外（postcss Unexpected }）。
5. **小步也要核对**：凡 Edit 时出现过一次报错/截断，后续每个小编辑落盘后立即读回被改区段核对（几行而已），连错两三次就换 Bash `python` 脚本方式写文件再通读。
6. ✅09-29 宣传页验证有效的写法：**(a)** 哨兵追加法——尾部放唯一 marker（`/* ==APPEND== */`），每轮只把 marker 替换为「≤40 行新段 + marker」，CSS/JS 全程零杂质；**(b)** 样板化 HTML 块（重复 6 行结构×N）是重灾区，Edit 重发反复在同一类行 glitch——直接换 python 锚点切割（`s.index(start锚)`/`s.index(end锚)` 定界）+ 干净字符串整体替换；**(c)** 每段落盘后 `grep -E "已知杂质token|"` 扫一遍，杂质集中在哪段一眼定位。
