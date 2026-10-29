---
name: bat-crlf-rule
description: "部署bat=GBK+CRLF+无chcp 65001——65001下cmd按字符数误记位置,中文行多必撕碎后续行;改bat用python二进制;碰bat/双击脚本先看"
metadata:
  node_type: memory
  type: project
  originSessionId: 1882bd78-581e-4a4e-9105-392afc57a92f
  modified: 2026-10-17T09:23:07.323Z
---

deploy/ 下三个 .bat(一键更新/一键重启/一键部署)的存活条件:**GBK 编码 + CRLF 行尾 + 不含 chcp 65001**。三者缺一,cmd 双击就碎。2026-10-10 已按此修好并真机验证。

**Why:** cmd 在 chcp 65001 下解析批处理时,内部文件位置按"字符数"而非"字节数"记账,每个含中文的行都会让位置指针漂移若干字节,漂到后面某行就从多字节字符中间开始执行(症状:ssh 整行没执行、`'39.132' 不是内部或外部命令`、`'/服务器是否在线...'` 这类碎片)。CRLF 只是必要条件(LF 行尾 + 中文必碎),不是充分条件;65001 的漂移是绝症。GBK + 默认 936 代码页是 cmd 原生路径,零漂移。

**How to apply:**
- 改 bat:用 python 二进制读写(`read_bytes().decode('gbk')` → 改 → `.encode('gbk')`),Edit/Write 工具是 UTF-8 会把 GBK 文件读成乱码、写回即毁
- 验证:做 stub 副本(sed 把 ssh/scp 行换成 echo)+ `@echo on` trace + `cmd //c` 真跑,看每行是否按序执行;输出经 `iconv -f gbk -t utf-8` 看
- 新建 bat 一律同规格(GBK+CRLF+无 chcp);中文行尽量短
- git-bash 的 sed/awk/od/grep 对 \r 有文本模式翻译会撒谎,验行尾用 `tr -dc '\r' < 文件 | wc -c`(bash 重定向是二进制)
- 相关坑:update.sh 只认 `dist.tgz`/`backend.tgz` 包名;`start.sh` 的 NODE_BIN 是模板占位(现带自愈回退);长 ssh 命令输出重定向到文件,别接 tail(管道缓冲会假死)。相关:[[pwa-mobile-install]]、[[deploy-ubuntu-single-machine]]
- 2026-10-16 tools/demo/start_demo.bat 同病发作(untracked 文件被存成 UTF-8+LF+chcp 65001,双击即碎),当时修回 GBK+CRLF;**该演示栈已于 2026-10-17 整体移除**(tools/demo 已删),此条留作病史。经验仍有效:bat 一律 GBK+CRLF 无 chcp;嵌套引号用 cd+set+模块入口 零引号写法;git-bash 跑 bat 输出重定向到文件避免管道挂起
