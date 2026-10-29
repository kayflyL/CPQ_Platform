---
name: github-access-channels
description: 本机直连github被墙;git代理127.0.0.1:10809(v2rayN)进程常没开;可用通道=gh-proxy.com镜像拉整仓、jsdelivr拉单文件
metadata:
  node_type: memory
  type: reference
  originSessionId: 7dcc3326-2d54-4287-9aeb-a6577d43aaae
  modified: 2026-10-23T06:36:15.190Z
---

Windows 本机（2026-10-23 实测）访问 GitHub 的通道状况：

- 直连 github.com：不通
- git 全局代理 `http://127.0.0.1:10809`（v2rayN 默认口）：配置在但代理进程经常没跑，`git clone` 会卡死在这
- **整仓下载可用**：`https://gh-proxy.com/https://github.com/<owner>/<repo>/archive/refs/heads/main.tar.gz`（实测 200）
- **单文件可用**：`https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/<path>`
- ghfast.top / ghproxy.net 当时不通；z.ai 的 web_reader MCP 也能读 github 页面（走其 relay）

拉 GitHub 东西之前先试代理端口是否活着，死了直接走 gh-proxy.com。
