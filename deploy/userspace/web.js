#!/usr/bin/env node
// CPQ 用户级前端服务:静态托管 dist + /api 反代(含 WebSocket),零依赖,免 root。
// 用法: node web.js   可用环境变量覆盖: PORT(默认5173) API(默认127.0.0.1:5174) DIST
//       可选 TLS: TLS_PORT(如5443) + TLS_CERT + TLS_KEY 同时给出时加开 HTTPS 门(安卓 PWA 安装的硬前提);
//       证书缺失/读不到只降级打日志,HTTP 照常。CA_FILE 给出时提供 GET /cpq-ca.crt 证书下载(手机装 CA 用)。
const http = require('http'), https = require('https'), fs = require('fs'), path = require('path'), net = require('net');
const PORT = +process.env.PORT || 5173;
const API = process.env.API || '127.0.0.1:5174';
const DIST = path.resolve(process.env.DIST || path.join(__dirname, 'frontend-dist'));
const TLS_PORT = +process.env.TLS_PORT || 0;
const TLS_CERT = process.env.TLS_CERT || '';
const TLS_KEY = process.env.TLS_KEY || '';
const CA_FILE = process.env.CA_FILE || '';
const [API_HOST, API_PORT] = API.split(':');
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.webp': 'image/webp',
  '.avif': 'image/avif', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
  '.otf': 'font/otf', '.eot': 'application/vnd.ms-fontobject', '.map': 'application/json',
  '.wasm': 'application/wasm', '.exr': 'application/octet-stream', '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json', '.vrm': 'model/gltf-binary', '.mp4': 'video/mp4',
  '.webm': 'video/webm', '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
};

function handleRequest(req, res) {
  if (req.url.startsWith('/api/')) return proxy(req, res);
  if (CA_FILE && req.url.split('?')[0] === '/cpq-ca.crt') return serveCa(res);
  let p;
  try { p = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch { res.writeHead(400); return res.end(); }
  let file = path.normalize(path.join(DIST, p));
  if (file !== DIST && !file.startsWith(DIST + path.sep)) { res.writeHead(403); return res.end(); }
  let st = null;
  try { st = fs.statSync(file); } catch {}
  if (!st || st.isDirectory()) file = path.join(DIST, 'index.html');   // SPA 路由回退
  const ext = path.extname(file).toLowerCase();
  const cache = file.includes(`${path.sep}assets${path.sep}`) ? 'public, max-age=31536000, immutable' : 'no-cache';
  const stream = fs.createReadStream(file);
  stream.on('open', () => { res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': cache }); stream.pipe(res); });
  stream.on('error', () => { res.writeHead(404); res.end('not found'); });
}

// 手机端一次性装 CA 根证书用(配合 install-help.html 引导页)
function serveCa(res) {
  fs.stat(CA_FILE, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); return res.end('ca not found'); }
    res.writeHead(200, {
      'Content-Type': 'application/x-x509-ca-cert',
      'Content-Disposition': 'attachment; filename="cpq-ca.crt"',
      'Content-Length': st.size,
      'Cache-Control': 'no-cache',
    });
    fs.createReadStream(CA_FILE).pipe(res);
  });
}

function proxy(req, res) {
  const up = http.request(
    { host: API_HOST, port: API_PORT, path: req.url, method: req.method, headers: { ...req.headers, host: `${API_HOST}:${API_PORT}` } },
    (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); }
  );
  up.on('error', () => { res.writeHead(502); res.end('backend down'); });
  req.pipe(up);
}

// WebSocket 升级:建立原始 TCP 管道,首包(含升级头)原样转发(HTTP/HTTPS 两个门共用)
function handleUpgrade(req, socket, head) {
  const up = net.connect(+API_PORT, API_HOST, () => {
    let out = `${req.method} ${req.url} HTTP/1.1\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) out += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    up.write(out + '\r\n');
    if (head.length) up.write(head);
    up.pipe(socket);
    socket.pipe(up);
  });
  up.on('error', () => socket.destroy());
  socket.on('error', () => up.destroy());
}

const server = http.createServer(handleRequest);
server.on('upgrade', handleUpgrade);
server.listen(PORT, '0.0.0.0', () => console.log(`cpq web :${PORT} -> api ${API_HOST}:${API_PORT}, dist ${DIST}`));

if (TLS_PORT && TLS_CERT && TLS_KEY) {
  try {
    const tlsServer = https.createServer({ cert: fs.readFileSync(TLS_CERT), key: fs.readFileSync(TLS_KEY) }, handleRequest);
    tlsServer.on('upgrade', handleUpgrade);
    tlsServer.listen(TLS_PORT, '0.0.0.0', () => console.log(`cpq web-tls :${TLS_PORT} -> api ${API_HOST}:${API_PORT}, cert ${TLS_CERT}`));
  } catch (e) {
    console.log('TLS 未启用:', e.message);
  }
}
