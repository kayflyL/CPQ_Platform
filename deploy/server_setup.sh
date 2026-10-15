#!/usr/bin/env bash
# CPQ 一键装机(Ubuntu 22.04/24.04) —— 由本地 deploy/一键部署.bat 上传后执行: sudo bash server_setup.sh
# 幂等:可重复运行;已有的 .env 与数据库数据不会被覆盖。
set -euo pipefail

APP_DIR=/opt/cpq
APP_USER=cpq
DB_USER=cpq
DB_NAME=cpq_platform

[ "$(id -u)" = 0 ] || { echo "请用 sudo 运行: sudo bash server_setup.sh"; exit 1; }
for f in /tmp/cpq_backend.tgz /tmp/cpq_frontend_dist.tgz /tmp/cpq_data.tgz /tmp/cpq_deploy.tgz /tmp/cpq_secrets.env; do
  [ -f "$f" ] || { echo "缺少 $f —— 先在本地跑 deploy/一键部署.bat"; exit 1; }
done
# LLM_API_KEY 等来自开发机 .env(不入仓库);Windows 生成,先去掉 CRLF
sed -i 's/\r$//' /tmp/cpq_secrets.env
. /tmp/cpq_secrets.env

echo "== 1/8 系统包 =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates python3-venv nginx ufw >/dev/null

echo "== 2/8 PostgreSQL 18(PGDG 源,与开发机同版本) =="
if ! apt-cache show postgresql-18 >/dev/null 2>&1; then
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
  apt-get update -qq
fi
apt-get install -y -qq postgresql-18 >/dev/null

echo "== 3/8 用户与代码落位 =="
id "$APP_USER" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d "$APP_DIR" "$APP_USER"
mkdir -p "$APP_DIR/frontend-dist" "$APP_DIR/data"
tar xzf /tmp/cpq_backend.tgz -C "$APP_DIR"
tar xzf /tmp/cpq_frontend_dist.tgz -C "$APP_DIR/frontend-dist"
tar xzf /tmp/cpq_data.tgz -C "$APP_DIR/data"

echo "== 4/8 数据库建库 + 迁入开发库数据 =="
DB_PASS=$(openssl rand -hex 16)
if [ -f "$APP_DIR/backend/.env" ]; then   # 重复运行:沿用旧密码,和 .env 保持一致
  DB_PASS=$(grep -oP '(?<=^POSTGRES_PASSWORD=).*' "$APP_DIR/backend/.env" | head -1)
fi
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  sudo -u postgres psql -qc "ALTER ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';"
else
  sudo -u postgres psql -qc "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';"
fi
TABLES=$(sudo -u postgres psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" "$DB_NAME" 2>/dev/null || echo NODB)
if [ "$TABLES" = "NODB" ]; then
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
  sudo -u postgres pg_restore -d "$DB_NAME" --no-owner --no-privileges --role="$DB_USER" /tmp/cpq_platform_*.dump
  echo "   空库已建,开发库数据已迁入"
elif [ "$TABLES" = "0" ]; then
  sudo -u postgres pg_restore -d "$DB_NAME" --no-owner --no-privileges --role="$DB_USER" /tmp/cpq_platform_*.dump
  echo "   开发库数据已迁入"
else
  echo "   库里已有数据,跳过导数据(防重复)"
fi

echo "== 5/8 Python 依赖 + Playwright(chromium) =="
[ -d "$APP_DIR/backend/.venv" ] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/backend/.venv"
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"
"$APP_DIR/backend/.venv/bin/playwright" install-deps chromium >/dev/null                  # root:apt 系统依赖
sudo -u "$APP_USER" "$APP_DIR/backend/.venv/bin/playwright" install chromium >/dev/null   # 浏览器本体进 cpq 的 ~/.cache

echo "== 6/8 backend/.env(机密,首次生成) =="
if [ ! -f "$APP_DIR/backend/.env" ]; then
  cat > "$APP_DIR/backend/.env" <<EOF
DEBUG=false
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_DB=$DB_NAME
DATA_PATH=$APP_DIR/data
JWT_SECRET=$(openssl rand -hex 32)
LLM_API_KEY=${LLM_API_KEY:-}
LLM_BASE_URL=${LLM_BASE_URL:-}
LLM_MODEL=${LLM_MODEL:-qwen-plus}
FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY:-}
EOF
  echo "   已生成(数据库密码与 JWT 自动生成,都在里面)"
else
  echo "   已存在,保持不动"
fi

echo "== 7/8 systemd + nginx + 防火墙 =="
# Windows 检出可能带 CRLF,systemd 不认,先归一
sed -i 's/\r$//' /tmp/deploy/cpq-backend.service /tmp/deploy/nginx-cpq.conf
cp /tmp/deploy/cpq-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cpq-backend >/dev/null 2>&1
cp /tmp/deploy/nginx-cpq.conf /etc/nginx/sites-available/cpq
ln -sf /etc/nginx/sites-available/cpq /etc/nginx/sites-enabled/cpq
rm -f /etc/nginx/sites-enabled/default
nginx -t -q && systemctl reload nginx
ufw allow OpenSSH >/dev/null
ufw allow 'Nginx Full' >/dev/null
ufw --force enable >/dev/null

echo "== 8/8 每日自动备份(保留14天) =="
mkdir -p /var/backups/cpq && chown postgres:postgres /var/backups/cpq
cat > /etc/cron.d/cpq-backup <<'CRON'
10 2 * * * postgres pg_dump -F c -f /var/backups/cpq/cpq_platform_$(date +\%Y\%m\%d).dump cpq_platform && find /var/backups/cpq -name "*.dump" -mtime +14 -delete
CRON
chmod 644 /etc/cron.d/cpq-backup

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/backend/.env"
sleep 2
STATUS=$(systemctl is-active cpq-backend || true)
IP=$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "=============================================="
echo " CPQ 部署完成!后端状态: $STATUS"
echo " 访问:  http://$IP/"
echo " 日志:  journalctl -u cpq-backend -f"
echo " 机密:  $APP_DIR/backend/.env(含自动生成的库密码/JWT)"
echo " 待办:  企业微信可信 IP 加上出口 IP: $IP"
echo "=============================================="
