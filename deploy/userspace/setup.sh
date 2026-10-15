#!/usr/bin/env bash
# CPQ userspace installer (no sudo). Target: Ubuntu, runs entirely under $HOME/cpq.
# Ports: pg 5499 / backend 5174 / frontend 5173. Inputs uploaded to ~/cpq first:
#   backend.tgz dist.tgz data.tgz secrets.env(LLE keys only) web.js start.sh.tpl
set -euo pipefail
CPQ="$HOME/cpq"; LOG="$CPQ/logs"; VENV="$CPQ/backend/.venv"
mkdir -p "$LOG" "$CPQ/frontend-dist"

echo "== 1/7 unpack =="
cd "$CPQ"
[ -d backend ] || tar xzf backend.tgz
tar xzf dist.tgz -C frontend-dist
tar xzf data.tgz -C data
NODE_BIN=$(command -v node)

echo "== 2/7 venv =="
cd "$CPQ/backend"
[ -d .venv ] || python3 -m venv .venv
"$VENV/bin/pip" install -q -i https://pypi.tuna.tsinghua.edu.cn/simple psycopg2-binary

echo "== 3/7 postgres binaries (zonky, self-contained) =="
cd "$CPQ/pg"
[ -x bin/initdb ] || {
  curl -fsSL -o pg.jar "https://maven.aliyun.com/repository/public/io/zonky/test/postgres/embedded-postgres-binaries-linux-amd64/16.4.0/embedded-postgres-binaries-linux-amd64-16.4.0.jar"
  python3 -m zipfile -e pg.jar . && rm pg.jar
  tar xJf postgres-linux-x86_64.txz && rm postgres-linux-x86_64.txz
}

echo "== 4/7 init cluster (trust first, flip to md5 after passwords) =="
PGPW=$(openssl rand -hex 16); echo "$PGPW" > "$CPQ/pg/pw.txt"; chmod 600 "$CPQ/pg/pw.txt"
[ -d data ] || {
  # NOTE: -U postgres is required: initdb defaults the superuser to the OS user name
  ./bin/initdb -U postgres -D data -E UTF8 --locale=C.UTF-8 --auth=trust >/dev/null
  ./bin/pg_ctl -D data -l "$LOG/pg.log" -o "-p 5499 -c listen_addresses=127.0.0.1" start
  sleep 1
}

echo "== 5/7 roles, database, schemas =="
"$VENV/bin/python" - <<'PYEOF'
import os, psycopg2
from psycopg2 import sql
pw = open(os.path.expanduser('~/cpq/pg/pw.txt')).read().strip()
c = psycopg2.connect(host='127.0.0.1', port=5499, user='postgres', password='x', dbname='postgres')
c.autocommit = True
cur = c.cursor()
cur.execute("SELECT 1 FROM pg_roles WHERE rolname='cpq'")
if cur.fetchone():
    cur.execute(sql.SQL("ALTER ROLE cpq LOGIN PASSWORD {}").format(sql.Literal(pw)))
else:
    cur.execute(sql.SQL("CREATE ROLE cpq LOGIN PASSWORD {}").format(sql.Literal(pw)))
cur.execute("SELECT 1 FROM pg_database WHERE datname='cpq_platform'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE cpq_platform OWNER cpq")
PYEOF
# switch local auth to md5 now that passwords exist
sed -i 's/trust/md5/g' data/pg_hba.conf && ./bin/pg_ctl -D data reload >/dev/null
"$VENV/bin/python" -c "
import psycopg2
pw = open('$CPQ/pg/pw.txt').read().strip()
c = psycopg2.connect(host='127.0.0.1', port=5499, user='cpq', password=pw, dbname='cpq_platform')
c.autocommit = True
cur = c.cursor()
for s in ['kp', 'l6', 'l6_history', 'opportunities', 'parts', 'rules']:
    cur.execute('CREATE SCHEMA IF NOT EXISTS ' + s + ' AUTHORIZATION cpq')
print('schemas ok')
"

echo "== 6/7 .env + start.sh =="
if [ ! -f "$CPQ/backend/.env" ]; then
  { echo "DEBUG=false"
    echo "POSTGRES_HOST=127.0.0.1"; echo "POSTGRES_PORT=5499"
    echo "POSTGRES_USER=cpq"; echo "POSTGRES_PASSWORD=$PGPW"
    echo "POSTGRES_DB=cpq_platform"; echo "DATA_PATH=$CPQ/data"
    echo "JWT_SECRET=$(openssl rand -hex 32)"
    cat "$CPQ/secrets.env"
  } > "$CPQ/backend/.env"
  chmod 600 "$CPQ/backend/.env"
fi
sed "s|__NODE_BIN__|$NODE_BIN|" "$CPQ/start.sh.tpl" > "$CPQ/start.sh"
chmod +x "$CPQ/start.sh"

echo "== 7/7 full deps (background) =="
"$VENV/bin/pip" install -q -i https://pypi.tuna.tsinghua.edu.cn/simple "psycopg[binary]"
nohup "$VENV/bin/pip" install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$CPQ/backend/requirements.txt" > "$LOG/pip.log" 2>&1 &
echo "SETUP-DONE (pip running in background, logs/pip.log)"
