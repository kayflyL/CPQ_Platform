# CPQ Platform 部署指南（Ubuntu）

> 最后更新：2026-10-10

单机形态：nginx 托管前端静态 + 反代 `/api`（含 WebSocket）→ uvicorn **单 worker**（FastAPI）→ 本机 PostgreSQL。
代码在服务器 `/opt/cpq`，运行用户 `cpq`，价格数据 `/opt/cpq/data`。

## 快车道：三个文件，点完即用

| 文件 | 干什么 |
|---|---|
| [server.txt](server.txt) | 填一行 `用户名@服务器IP`（两个 bat 共用，只填这一次） |
| [一键部署.bat](一键部署.bat) | **首次部署**：构建前端 → 打包 → 导出开发库 → 上传 → 服务器自动装完（PG/依赖/chromium/nginx/systemd/备份定时） |
| [一键更新.bat](一键更新.bat) | **日常发布**：构建前端 → 打包 → 上传 → 重启后端，1-2 分钟 |

首次点完后，脚本末尾会打印访问地址和后端状态；然后按下面「验证清单」打勾。
机密（数据库密码/JWT/LLM key）全部自动处理：LLM 配置从开发机 `backend/.env` 提取，数据库密码和 JWT 服务器端自动生成，**不进仓库**。

想免输密码（可选，一次性）：`ssh-keygen -t ed25519 -N "" -f %USERPROFILE%\.ssh\id_ed25519`（已有关键跳过），然后
`type %USERPROFILE%\.ssh\id_ed25519.pub | ssh 用户名@IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`。

服务器侧的完整安装脚本：[server_setup.sh](server_setup.sh)，幂等可重跑。它做的事：

1. apt 装 nginx / python3-venv / ufw → PGDG 源装 PostgreSQL 18（与开发机同版本）
2. 建 `cpq` 系统用户，解包代码到 `/opt/cpq`（`.env`/`.venv` 不在包里，更新时不被覆盖）
3. 建库建角色（密码自动生成），空库才迁入开发库数据（防重复导）
4. venv + requirements.txt + Playwright chromium（系统依赖与浏览器分两步装）
5. 生成 `/opt/cpq/backend/.env`（含 DATA_PATH=/opt/cpq/data、JWT_SECRET 等 12 键）
6. systemd（[cpq-backend.service](cpq-backend.service)，单 worker + UTF-8 + 崩溃自拉起）+ nginx（[nginx-cpq.conf](nginx-cpq.conf)）+ ufw 只开 22/80/443
7. `/etc/cron.d/cpq-backup`：每天 2:10 pg_dump，保留 14 天

## 验证清单（部署完逐条打勾）

| 项 | 做法 | 坏了查什么 |
|---|---|---|
| 后端活着 | 服务器上 `curl -s http://127.0.0.1:8000/docs` 有输出 | `journalctl -u cpq-backend -n 100` |
| 前端可开 | 浏览器 `http://<服务器IP>/` 出登录页 | nginx 配置、`nginx -t` |
| 登录 | admin 账号登录进工作台 | `.env` 的 `JWT_SECRET` |
| PDF 打印/导出 | 报价页导出规格书 PDF | Playwright 两步没装全 |
| 助手聊天 | 全局浮动助手发消息，流式回复 | nginx WebSocket 升级头 |
| 站内通知 | 顶栏铃铛实时亮 | 同上 `/api/notifications/ws` |
| 企微通知 | 触发一条外推通知 | **服务器出口 IP 未进企微可信 IP** |
| 语义检索 | 配件推荐正常召回 | fastembed 模型下载；降级词法不致命 |

## 慢车道：手工分步（排障 / 不想用 bat 时）

与 `server_setup.sh` 等价。本地打包（产物进 `D:\CPQ_Archive\`，不进仓库）：

```bash
cd /d/CPQ_Platform_V1/frontend && npm run build
tar czf /d/CPQ_Archive/cpq_frontend_dist.tgz -C dist .
tar czf /d/CPQ_Archive/cpq_backend.tgz --exclude=.venv --exclude=.env --exclude=__pycache__ --exclude=tmp --exclude=*.db -C /d/CPQ_Platform_V1 backend
tar czf /d/CPQ_Archive/cpq_data.tgz -C /d/Quotation_Automation config.json
export PGPASSWORD='<开发库密码>'
"/c/Program Files/PostgreSQL/18/bin/pg_dump.exe" -U postgres -d cpq_platform -F c --no-owner --no-privileges -f /d/CPQ_Archive/cpq_platform_$(date +%Y%m%d).dump
```

上传后在服务器按 `server_setup.sh` 的 8 步执行（或直接 `sudo bash` 跑它）。
后端从 `DATA_PATH` 只读 `config.json` 一个文件（pricing_engine / quote_service），`D:\Quotation_Automation` 其余是旧项目不用迁。
schema 迁移全自动：startup 的 `create_all` + `ensure_*` 在空库上自己长全表，**更新发版不用手工动库**。

## 故障排查速查

- **启动崩、日志见 UnicodeEncodeError** → service 文件里 `Environment=PYTHONUTF8=1` 被删了
- **打印/PDF 返回 500** → chromium 没装全：`sudo .venv/bin/playwright install-deps chromium` + `sudo -u cpq .venv/bin/playwright install chromium`
- **聊天/通知 WS 连不上** → 浏览器控制台看 ws 状态；nginx conf 的 Upgrade 头是否还在
- **skill 长任务中途断** → nginx `proxy_read_timeout` 被改小（需覆盖数分钟级任务）
- **企微通知静默失败** → 服务器出口 IP 进企微可信 IP
- **restore 报版本不兼容** → 确认用的是 PGDG 18（脚本第 2 步）

## 用户级部署（无 sudo，**当前线上形态**）

内网服务器 10.32.39.132，kayfly 无 sudo/docker，全部装在家目录。端口自定义为避开公用服务器的拥挤段：

- `~/cpq/pg` —— 用户级 PostgreSQL 16（Zonky 自包含二进制，仅监听 127.0.0.1:**5499**）
- `~/cpq/backend` —— uvicorn 127.0.0.1:**5174**（单 worker；机密在 `~/cpq/backend/.env`，12 键）
- `~/cpq/frontend-dist` + `~/cpq/web.js` —— node 零依赖静态托管 + `/api` 反代（含 WS），0.0.0.0:**5173**
- 保活：cron 每分钟跑 `~/cpq/start.sh`（挂了自动拉起，服务器重启后也靠它恢复）
- 日志：`~/cpq/logs/{pg,backend,web,boot,pip}.log`；完整安装脚本 [userspace/setup.sh](userspace/setup.sh)

用户级日常更新：**双击 [一键更新.bat](一键更新.bat)**（构建前端 → 打包 → 免密上传 → 服务器 `update.sh` 自动落位重启并自检，全程一次点击）。
只重启不更新：**双击 [一键重启.bat](一键重启.bat)**（复用服务器 `update.sh` 的杀后端+拉起逻辑；前端是静态文件即改即生效，无需重启）。服务器整机重启后**无需任何操作**——cron 看门狗每分钟检查并在开机后约 1 分钟内自动拉起三件套。

免密已配好（2026-10-10）：本机 `~/.ssh/cpq_deploy` 密钥已装进服务器 `authorized_keys`，`~/.ssh/config` 里写了 `Host 10.32.39.132 → User kayfly`。换电脑时重做这两步即可。

手工更新（等价于 bat 干的事，排障用）：

```bash
# 开发机
cd /d/CPQ_Platform_V1/frontend && npm run build
tar czf /d/CPQ_Archive/dist.tgz -C dist .
tar czf /d/CPQ_Archive/backend.tgz --exclude=.venv --exclude=.env --exclude=__pycache__ --exclude=tmp --exclude=*.db -C /d/CPQ_Platform_V1 backend
scp /d/CPQ_Archive/backend.tgz /d/CPQ_Archive/dist.tgz 10.32.39.132:cpq/
ssh 10.32.39.132 "bash ~/cpq/update.sh"
```

已知坑（都已踩过并修在脚本里）：initdb 必须加 `-U postgres`（否则超用户名跟随 OS 用户）；SQLAlchemy 2.1 起 `postgresql://` 默认走 psycopg v3，必须装 `psycopg[binary]`；空库要预建 6 个 schema（kp/l6/l6_history/opportunities/parts/rules）；打包必须 `--exclude=.env`（曾把开发机密钥打进包上传）；**三个 .bat 是 GBK 编码 + CRLF 行尾且必须保持**（cmd 在 chcp 65001 下解析中文行会按字符数误记文件位置，中文行一多就把后续行撕成碎片执行——2026-10-10 一键重启双击报碎片已修；改 bat 用 python 二进制读写转 GBK，勿用文本工具直接编辑，也勿加回 chcp 65001）；**发版包名必须是 `dist.tgz`/`backend.tgz`**（update.sh 按这两个名字解包，2026-10-10 前包名错位导致 bat 从未真正发过版）；`userspace/start.sh` 的 `NODE_BIN` 是模板占位，setup.sh 安装时替换，现带自愈回退（直接发模板也不宕机）。

## 手机桌面 App（PWA）与 HTTPS 门（5443）

安卓 Chrome 只肯在 HTTPS 站点提供「安装应用」，所以前端有两个门，内容完全相同：

| 门 | 协议 | 用途 |
|---|---|---|
| **5173** | HTTP | 老入口，永远保留；没装证书的手机照常用 |
| **5443** | HTTPS | 装了 CA 证书的安卓手机走这里，才能安装成桌面 App |

启用步骤（服务器上一次性）：

```bash
bash ~/cpq/make_certs.sh          # 自签 CA + 服务器证书(10.32.39.132),产物在 ~/cpq/certs/
# 之后 start.sh / 一键重启.bat 拉起 web.js 时自动带上 5443;可用 update.sh 末尾的 frontend-tls 自检验证
```

手机端引导：访问 `http://10.32.39.132:5173/install-help.html`（分步说明 + CA 证书下载链接，自动识别安卓/iPhone）。要点：安卓每台手机装一次 CA 证书后需彻底重启 Chrome；iPhone 不用装证书，Safari 分享→添加到主屏幕即可全屏。自签证书首次访问 5443 会提示"不安全"，装完 CA 后消失。

相关文件：[userspace/make_certs.sh](userspace/make_certs.sh)（签证书）、[userspace/web.js](userspace/web.js)（TLS 门 + `/cpq-ca.crt` 下载路由）、前端 `public/manifest.webmanifest` + `public/icons/`（PWA 清单与图标）、`public/install-help.html`(引导页)。注意：**一键更新.bat 会同时上传 web.js / start.sh / make_certs.sh / update.sh 并重启前端进程**（发布时 5173 有 1~2 秒瞬断，属正常）。

## 已知取舍

- **单 worker 是硬约束**：聊天运行时/通知中心是进程内单例。并发不够先垂直升配；要多 worker 必须先把进程内状态外置。
- 一键启动.bat / start_backend.bat 是开发机专用，与服务器无关。

## 数据通道与环境纪律（2026-10-30 切库丢交付流事故后立）

本地（开发）与线上各自持有自己的库。数据分三类，三条通道，**永不混用**：

| 类 | 例子 | 权威 | 通道 |
|---|---|---|---|
| 结构（表/列/索引） | 新功能的列 | 本地开发时 | **boot 自愈**：startup.py 加 `ensure_*` 接进启动序列——改 model 加列，同一提交必须带 ensure（code review 必查项），线上重启自动跟上 |
| 种子/配置（工作流定义、权限目录、字典） | 交付流的图+节点配置 | **git（backend/seeds/）** | `scripts/export_flow.py <key>` 导出进 git；缺流的环境 `scripts/import_flow.py seeds/flows/<key>.json` 灌入（空缺才灌，不覆盖用户改动） |
| 业务事实（商机/报价/配件/评论） | 线上每天新增的商机 | **线上（唯一权威）** | 只在线上产生；本地要真实数据感 = **单向拉进本地**（白名单表+按业务键 upsert）；线上修数走 `backfill_*` 脚本（进 git、幂等） |

### 拉业务数据的六守则

1. **白名单表**：脚本显式声明允许写的表；绝不同步 `rules.reasoning_flow` / `rules.skill_catalog` / `rules.reasoning_node_config`（工作流是图纸，不在业务同步范围）。
2. **按业务键 upsert**（料号/客户+单号）；绝不做"新数据里没有的行就删掉"；下架打标不物理删。
3. **三禁区**：`TRUNCATE`（尤其 CASCADE）/ `DROP` / 整 schema dump-restore——同步脚本里不许出现。
4. **字段口径显式化**：哪些列以新数据为准、哪些保留本地人工改动，写进脚本注释（覆盖人工输入必须显式声明——2026-10-22 既有规矩）。
5. **显式 id 插入后必跑序列校准**（切库撞键教训）。
6. **同步前后跑守卫**：`python backend/scripts/sync_guard.py before --tables <表>` → 同步 → `after`——行数变少自动报警 + 流点名自检。同步前备份自动落 `.scratch/sync_guard_<时间戳>/`。

### 流点名（任何切库/拉库/换环境后必看）

- 服务启动时自动跑（启动日志找 `✅ 流点名自检` 或 `⚠️ 缺流`）；
- 手动：`python backend/scripts/sync_guard.py after --tables <表>`（末尾带点名）；
- 服务器上核对：`sudo -u postgres psql -d cpq_platform -c "SELECT id,skill_key,version,is_active FROM rules.reasoning_flow ORDER BY id"`——对着代码注册的 flow_key 逐个点名。

> 事故备忘：2026-10-24 切库合并漏带交付流三表数据行，10-30 靠 `CPQ_Archive/local_backup_20261023.dump` 考古回迁。根因=合并没按表清单对账 + 种子未进 git。本节即该事故的制度化产出。
