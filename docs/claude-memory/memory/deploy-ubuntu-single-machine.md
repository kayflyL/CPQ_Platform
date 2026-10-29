---
name: deploy-ubuntu-single-machine
description: "部署现状:内网10.32.39.132 kayfly用户级部署,端口5173/5443(TLS门)/5174/5499;碰部署/发版先看"
metadata:
  node_type: memory
  type: project
  originSessionId: 553d0a3d-46f1-4241-b92b-a7a90ec6eb78
  modified: 2026-10-10T16:51:19.437Z
---

部署现状(2026-10-10 上线):内网共享服务器 **10.32.39.132**(Ubuntu 24.04,128核503G,kayfly **无 sudo/无 docker**),全部装在家目录 `~/cpq/`。端口:前端 node 零依赖静态+反代 **5173**(web.js,另挂 **5443** HTTPS 门=自签CA,见 [[pwa-mobile-install]]) → 后端 uvicorn 单 worker **5174**(127.0.0.1) → 用户级 PostgreSQL16(Zonky 二进制) **5499**(仅本机)。保活=cron 每分钟跑 `~/cpq/start.sh`。部署套件权威在 `deploy/`(sudo 版:DEPLOY.md+server_setup.sh+nginx+systemd)与 `deploy/userspace/`(无 sudo 版:setup.sh/web.js/start.sh)。

**Why:** 共享服务器 80 被 nginx 占、8000 被 laya-serve 占、5432 是 1Panel 管的别人的 PG(无凭据),故全端口自定义+自带库;进程内单例(ChatSessionRuntime/notification_hub)锁死单 worker;前端 axios 全相对 /api,同源反代零 CORS。

**How to apply:** 发版=双击 `deploy/一键更新.bat`;只重启=双击 `deploy/一键重启.bat`(都走服务器 ~/cpq/update.sh,免密已配:本机 ~/.ssh/cpq_deploy 已装服务器 authorized_keys,~/.ssh/config 有 Host 10.32.39.132 条目);手工等价=build+tar(--exclude=.env!)+scp 到 cpq/+`bash ~/cpq/update.sh`。⚠️**包名陷阱(2026-10-11 踩坑)**:update.sh 只认短名 `dist.tgz`/`backend.tgz`,若 scp 落名是 `cpq_dist.tgz`/`cpq_backend.tgz`,update.sh 照样重启但**代码从不解包(假发布)**——手工发版必须先 `mv cpq_dist.tgz dist.tgz`;验收=对比 `curl http://10.32.39.132:5173/` 与本地 dist/index.html 的 assets hash(minified bundle 里 grep 局部变量名恒为 0,别当修复缺失)。VPN 链路慢,scp/update.sh 挂 2-5 分钟是常态,ssh 命令易超时转后台。开发库数据已迁完(2026-10-10,pg_dump 3.5MB 经 sshtunnel 隧道 + 本地 pg_restore18 → 服务器 PG16,107/107 表;开发库 postgres 密码=961216,用户曾误记 961106)。踩过的坑:①initdb 必须加 `-U postgres`(默认超用户名跟随 OS 用户);②SQLAlchemy 2.1 起 postgresql:// 默认走 psycopg v3,必须装 psycopg[binary];③空库要预建 6 个 schema(kp/l6/l6_history/opportunities/parts/rules)+public;④pack 泄漏:backend.tgz 曾带出开发机 .env(已修 exclude,服务器上已删)。待办:企微可信 IP 未加服务器出口;DB 无异地备份(建议补 pg_dump cron)。相关:[[spec-print-server-pdf]]、[[wecom-notify-channel]]、[[chat-session-runtime]]、[[cpq-db-direct-query]]。
