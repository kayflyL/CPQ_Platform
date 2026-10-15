#!/usr/bin/env bash
# CPQ 用户级一键拉起:PG(5499) -> 后端(5174) -> 前端(5173);已在跑的自动跳过。
# cron 每分钟调它即是看门狗,无需 root。
set -u
CPQ="$HOME/cpq"
LOG="$CPQ/logs"
mkdir -p "$LOG"
NODE_BIN="__NODE_BIN__"
# 模板占位自愈:setup.sh 安装时会 sed 替换成真实路径;若模板被直接发到服务器,
# 回落到 PATH/系统 node,前端服务不至于起不来(2026-10-10 曾因裸模板覆盖致 5173 宕机)
if [ ! -x "$NODE_BIN" ]; then
  NODE_BIN="$(command -v node || echo /usr/bin/node)"
fi

# 1. PostgreSQL
if ! "$CPQ/pg/bin/pg_ctl" -D "$CPQ/pg/data" status >/dev/null 2>&1; then
  "$CPQ/pg/bin/pg_ctl" -D "$CPQ/pg/data" -l "$LOG/pg.log" -o "-p 5499 -c listen_addresses=127.0.0.1" start >>"$LOG/boot.log" 2>&1
  sleep 1
fi

# 2. 后端(单 worker 铁律:聊天运行时/通知中心是进程内单例)
# nohup 补 </dev/null:非交互 ssh 下 nohup 不代管 stdin,进程会攥住 ssh 管道让会话永不关闭
if ! ss -tln | grep -q ':5174 '; then
  cd "$CPQ/backend" && nohup "$CPQ/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 5174 </dev/null >>"$LOG/backend.log" 2>&1 &
fi

# 3. 前端(5173 HTTP 常开;证书就位时 web.js 自动加开 5443 HTTPS 门,安卓 PWA 安装要求 HTTPS)
if ! ss -tln | grep -q ':5173 '; then
  cd "$CPQ" && TLS_PORT=5443 TLS_CERT="$CPQ/certs/server.crt" TLS_KEY="$CPQ/certs/server.key" CA_FILE="$CPQ/certs/ca.crt" nohup "$NODE_BIN" web.js </dev/null >>"$LOG/web.log" 2>&1 &
fi
