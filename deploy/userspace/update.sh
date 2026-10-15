#!/usr/bin/env bash
# CPQ 更新落位:解包新代码/前端 + 重启后端。本地一键更新.bat 把包传到 ~/cpq/ 后调我。
# 幂等:没有包就只做重启;包里没有 .env/.venv,服务器上的机密与环境不动。
set -euo pipefail
cd "$HOME/cpq"
[ -f backend.tgz ] && { tar xzf backend.tgz && rm backend.tgz; }
[ -f dist.tgz ] && { tar xzf dist.tgz -C frontend-dist && rm dist.tgz; }
ps -ef | grep "uvicorn app" | grep -v grep | awk '{print $2}' | xargs -r kill
# 前端进程也随发版重启(静态文件本身即改即生效,这里是让 web.js/start.sh 的改动生效);start.sh 会拉起
ps -ef | grep "node web.js" | grep -v grep | awk '{print $2}' | xargs -r kill
sleep 1
bash "$HOME/cpq/start.sh"
sleep 8
curl -s -o /dev/null -w "backend: %{http_code}\n" http://127.0.0.1:5174/docs
curl -s -o /dev/null -w "frontend: %{http_code}\n" http://127.0.0.1:5173/
# HTTPS 门自检(证书未生成时降级为提示,不算失败)
if [ -f "$HOME/cpq/certs/server.crt" ]; then
  curl -s -o /dev/null -w "frontend-tls: %{http_code}\n" --cacert "$HOME/cpq/certs/ca.crt" "https://${CPQ_FRONT_IP:-10.32.39.132}:5443/"
else
  echo "frontend-tls: 未启用(先在服务器跑 bash ~/cpq/make_certs.sh)"
fi
