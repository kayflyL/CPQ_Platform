#!/usr/bin/env bash
# 自签 CA + 服务器证书:内网 HTTPS 门(5443)用,安卓 Chrome 只有走 HTTPS 才肯提供「安装应用」。
# 用法: bash make_certs.sh [IP或域名,多个逗号分隔,默认 10.32.39.132]
# 产物在 ~/cpq/certs/;手机只需装 ca.crt 一次(引导页 install-help.html 有分步说明),
# 之后换发服务器证书不用重装手机。已生成过则复用旧 CA,只换发服务器证书。
set -euo pipefail

CPQ="$HOME/cpq"
DIR="$CPQ/certs"
IPS="${1:-10.32.39.132}"
mkdir -p "$DIR"

# 1. 根 CA(10 年;已存在则复用——手机装的就是它,复用才能免重装)
if [ ! -f "$DIR/ca.crt" ] || [ ! -f "$DIR/ca.key" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$DIR/ca.key" -out "$DIR/ca.crt" -days 3650 \
    -subj "/CN=CPQ Intranet CA" >/dev/null 2>&1
  echo "已生成根 CA: $DIR/ca.crt"
else
  echo "复用已有根 CA: $DIR/ca.crt"
fi

# 2. 服务器证书 SAN:本机回环 + 指定 IP/域名
SAN="DNS:localhost,IP:127.0.0.1"
IFS=',' read -r -a ITEMS <<< "$IPS"
for item in "${ITEMS[@]}"; do
  SAN="$SAN,IP:$item"
done

openssl req -newkey rsa:2048 -nodes \
  -keyout "$DIR/server.key" -out "$DIR/server.csr" \
  -subj "/CN=CPQ Server" >/dev/null 2>&1
openssl x509 -req -in "$DIR/server.csr" \
  -CA "$DIR/ca.crt" -CAkey "$DIR/ca.key" -CAcreateserial \
  -days 825 -out "$DIR/server.crt" \
  -extfile <(printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth\n' "$SAN") >/dev/null 2>&1
rm -f "$DIR/server.csr"
chmod 600 "$DIR/ca.key" "$DIR/server.key"

echo "已签发服务器证书: $DIR/server.crt(SAN: $SAN)"
echo "手机端安装文件:   $DIR/ca.crt(经 http://<服务器IP>:5173/cpq-ca.crt 分发)"
