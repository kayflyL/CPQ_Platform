# Claude 桌面端频繁断流「Stream ended without receiving any events」——根因与自愈中继方案

> 2026-11-03 · Windows 11 · Claude 桌面应用（Claude Code 引擎）· 上游 = cloudprime（api.cloudprime.com.cn:5567，New API 中转）

## 一、问题现象

- 桌面端 Claude Code 频繁报错，两种形态：
  - `API returned an empty or malformed response (HTTP 200) ... This was the non-streaming retry of streaming request ... no_events, StreamNoEventsError; 0 stream events received`（长形态）
  - `Stream ended without receiving any events`（短形态）
- 一会好一会坏：同一个会话，有的轮次正常，有的轮次连点 Try again 都过不去。
- 同事用 Trae 直连同一个上游（cloudprime）、同一个模型（glm-5.3-flash），却基本稳定——曾长期误导向「上游通道烂了」或「换模型」，均被证伪。

## 二、链路与根因

原链路：**桌面应用 → cc-switch 本地代理（127.0.0.1:15721）→ cloudprime（池化通道轮询）**

根因共四条，层层叠加：

| # | 根因 | 实证 |
|---|------|------|
| 1 | cloudprime 是 New API 中转，背后轮询一池通道，**池里混着死通道**：返回 HTTP 200 但 SSE 流零事件、数秒内收场 | cc-switch 请求日志：同一分钟内 7 发请求全部「状态 200、无首字节、0 token」秒死；同时段 10 万 token 大请求首字节仅 0.9s 正常完成——按载荷/通道抛硬币 |
| 2 | cloudprime 的**非流式（stream:false）路径 100% 死**：恒定返回 683 字节「合法 Message 壳但 content 为空」的 JSON | 直连实测 3/3 发全空；另一同事实测 0/6 |
| 3 | 桌面客户端默认行为：流式失败后**自动降级改发一次非流式请求** → 撞上必死的非流式路径 → 可恢复的小故障被升级成必然报错 | 长形态报错自述 "This was the non-streaming retry of streaming request" |
| 4 | cc-switch 对 200 空响应**不重试、不告警**，直接透传空流；其日志对这种死法全绿，极具迷惑性 | 日志无任何 WARN 但客户端持续报错 |

**排查中被证伪的方向**（留作记录，别再走）：① cc-switch 首字节超时 90s——调到 600s 后依旧报错（死法是秒级空 200，不是超时）；② 升级 cc-switch 3.19.2 → 4.0.25——依旧报错，代理软件版本因素排除；③ 换模型——被否决，且与根因无关。

**Trae 稳定的真相**：同池同模型，它在客户端内部把空响应就地吞掉、静默重试，只有拿到真内容才呈现——本质是重试策略差异，不是通道差异。

## 三、解决方案（双层防护，互不冲突）

- **层 1｜客户端环境变量**：关掉「降级非流式」这条必死路 + 把客户端重试从 2 次提到 8 次。
- **层 2｜本地空响应重试中继**：一个零依赖 Node 脚本，桌面应用直连它，它转发 cloudprime；流式 200 缓冲到收到第一个 SSE 事件才放行，空流/连接错/429/5xx 自动重发（最多 5 次），模型名自动映射。**同事只需部署这一份脚本即可复刻全部行为。**

## 四、具体执行步骤

### 0. 前置

- 已装 Node.js（≥18；`node -v` 验证）。
- 准备好自己的 cloudprime API Key（sk- 开头，下文称 `<你的KEY>`）。

### 1. 设置用户级环境变量（关必死降级 + 加重试）

PowerShell 执行：

```powershell
[Environment]::SetEnvironmentVariable('CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK','1','User')
[Environment]::SetEnvironmentVariable('CLAUDE_CODE_MAX_RETRIES','8','User')
```

（也可在「设置 → 系统 → 高级系统设置 → 环境变量 → 用户变量」手工添加同名变量。）

### 2. 部署中继脚本

新建目录 `C:\Users\<你>\.claude-tools\`，将下面源码存为 `ccp-relay.js`，**把 `UPSTREAM_KEY` 改成你自己的 Key**（注意：脚本含明文 Key，不要提交进任何仓库）：

```js
// ccp-relay: 本地空响应重试中继
// 桌面应用 -> 127.0.0.1:15722 -> api.cloudprime.com.cn:5567
// 行为: 上游返回 200 但 SSE 零事件(死通道典型症状)时, 就地吞掉自动重发, 拿到真内容才放行
const http = require('http');
const fs = require('fs');
const path = require('path');

const LISTEN_PORT = 15722;
const UPSTREAM_HOST = 'api.cloudprime.com.cn';
const UPSTREAM_PORT = 5567;
const UPSTREAM_KEY = 'sk-替换成你自己的KEY';
const MAX_RETRIES = 12;
const FIRST_EVENT_TIMEOUT_MS = 300000; // 首事件等待上限(推理模型首字节可能慢), 超时视为死响应
// 退避序列(秒): 死通道按时间窗成批出现, 铺开重试间隔以跨越死亡窗口
const BACKOFF_S = [0.3, 0.8, 1.5, 3, 5, 8, 10, 10, 10, 10, 10];
const backoffMs = (attempt) => Math.round((BACKOFF_S[Math.min(attempt - 1, BACKOFF_S.length - 1)] || 10) * 1000);
const LOG_FILE = path.join(__dirname, 'relay.log');

// 模型映射: 桌面请求携带 claude-* 名称, 上游需要 glm-* 名称
const MODEL_MAP = {
  'claude-sonnet-5': 'glm-5.1',
  'claude-opus-5': 'glm-5.3-flash',
  'claude-fable-5': 'glm-5.3-flash',
  'claude-haiku-5-5': 'glm-5.3-flash',
};

function log(msg) {
  const line = `[${new Date().toLocaleString('sv-SE')}] ${msg}`;
  console.log(line);
  fs.appendFile(LOG_FILE, line + '\n', () => {});
}

function mapModel(bodyBuf) {
  try {
    const j = JSON.parse(bodyBuf.toString('utf8'));
    if (j && typeof j.model === 'string') {
      const mapped = MODEL_MAP[j.model] || (j.model.startsWith('claude-') ? 'glm-5.3-flash' : j.model);
      if (mapped !== j.model) {
        log(`model ${j.model} -> ${mapped}`);
        j.model = mapped;
        return Buffer.from(JSON.stringify(j));
      }
    }
    return bodyBuf;
  } catch {
    return bodyBuf; // 非 JSON 体原样透传
  }
}

// 向上游发一次请求; resolve(response) 或 reject(Error)
function upstreamOnce(reqUrl, method, headers, bodyBuf, clientReq) {
  return new Promise((resolve, reject) => {
    const h = { ...headers };
    delete h.host;
    delete h['content-length'];
    delete h['accept-encoding'];
    h.host = UPSTREAM_HOST;
    h['accept-encoding'] = 'identity';
    h.authorization = `Bearer ${UPSTREAM_KEY}`;
    h['content-length'] = bodyBuf.length;
    const upstreamReq = http.request(
      { host: UPSTREAM_HOST, port: UPSTREAM_PORT, path: reqUrl, method, headers: h },
      (res) => resolve(res)
    );
    upstreamReq.setTimeout(0); // 不限总时长, 思考多久都等
    upstreamReq.on('error', reject);
    clientReq.on('close', () => { if (!upstreamReq.writableEnded) upstreamReq.destroy(new Error('client aborted')); });
    upstreamReq.end(bodyBuf);
  });
}

const server = http.createServer(async (clientReq, clientRes) => {
  const chunks = [];
  clientReq.on('data', (c) => chunks.push(c));
  clientReq.on('end', async () => {
    const bodyBuf = mapModel(Buffer.concat(chunks));
    const started = Date.now();
    let attempt = 0;
    while (true) {
      attempt++;
      let res;
      try {
        res = await upstreamOnce(clientReq.url, clientReq.method, clientReq.headers, bodyBuf, clientReq);
      } catch (err) {
        if (clientReq.destroyed) return; // 客户端已断开
        log(`${clientReq.method} ${clientReq.url} attempt=${attempt} conn-error: ${err.message}`);
        if (attempt >= MAX_RETRIES) {
          clientRes.writeHead(502, { 'content-type': 'application/json' });
          clientRes.end(JSON.stringify({ error: { type: 'relay_exhausted', message: `upstream unreachable after ${attempt} attempts: ${err.message}` } }));
          return;
        }
        await new Promise((r) => setTimeout(r, backoffMs(attempt)));
        continue;
      }

      const status = res.statusCode;
      // 非 200: 429/5xx 重试, 其余原样透传
      if (status !== 200) {
        if ((status === 429 || status >= 500) && attempt < MAX_RETRIES) {
          res.resume();
          log(`${clientReq.method} ${clientReq.url} attempt=${attempt} status=${status} -> retry`);
          await new Promise((r) => setTimeout(r, backoffMs(attempt)));
          continue;
        }
        log(`${clientReq.method} ${clientReq.url} attempt=${attempt} status=${status} -> passthrough`);
        clientRes.writeHead(status, res.headers);
        res.pipe(clientRes);
        return;
      }

      const isStream = /text\/event-stream/i.test(res.headers['content-type'] || '');
      if (!isStream) {
        // 非流式 200: 整体收完, 空体视为死响应重试
        const outcome = await new Promise((resolve) => {
          const parts = [];
          let done = false;
          res.on('data', (c) => { if (!done) parts.push(c); });
          res.on('end', () => { if (!done) { done = true; resolve({ dead: Buffer.concat(parts).length === 0, full: Buffer.concat(parts) }); } });
          res.on('error', () => { if (!done) { done = true; resolve({ dead: true, full: Buffer.alloc(0) }); } });
          clientReq.on('close', () => { if (!done) { done = true; resolve({ dead: true, aborted: true, full: Buffer.alloc(0) }); } });
        });
        if (outcome.aborted) return;
        if (outcome.dead && attempt < MAX_RETRIES) {
          log(`${clientReq.method} ${clientReq.url} attempt=${attempt} 200-empty(non-stream) -> retry`);
          await new Promise((r) => setTimeout(r, backoffMs(attempt)));
          continue;
        }
        log(`${clientReq.method} ${clientReq.url} attempt=${attempt} ok non-stream ${outcome.full.length}B ${Date.now() - started}ms`);
        const hh = { ...res.headers };
        delete hh['content-length'];
        hh['content-length'] = outcome.full.length;
        clientRes.writeHead(status, hh);
        clientRes.end(outcome.full);
        return;
      }

      // 流式 200: 缓冲到首个 SSE data 事件才放行; 零事件收场 = 死响应, 重试
      const outcome = await new Promise((resolve) => {
        let buffered = [];
        let sawEvent = false;
        let done = false;
        const timer = setTimeout(() => { if (!done) { done = true; resolve({ dead: true, reason: 'first-event-timeout' }); res.destroy(); } }, FIRST_EVENT_TIMEOUT_MS);
        res.on('data', (c) => {
          if (sawEvent) return;
          buffered.push(c);
          const s = Buffer.concat(buffered).toString('latin1');
          if (/data:/.test(s)) {
            sawEvent = true;
            const prefix = Buffer.concat(buffered);
            clearTimeout(timer);
            if (!done) { done = true; resolve({ dead: false, prefix }); }
          }
        });
        res.on('end', () => { if (!done) { done = true; clearTimeout(timer); resolve({ dead: true, reason: 'closed-without-events' }); } });
        res.on('error', () => { if (!done) { done = true; clearTimeout(timer); resolve({ dead: true, reason: 'stream-error' }); } });
        clientReq.on('close', () => { if (!done) { done = true; clearTimeout(timer); resolve({ dead: true, reason: 'client-aborted' }); } });
      });

      if (!outcome.dead) {
        log(`${clientReq.method} ${clientReq.url} attempt=${attempt} ok stream first-byte ${Date.now() - started}ms`);
        clientRes.writeHead(status, res.headers);
        if (outcome.prefix && outcome.prefix.length) clientRes.write(outcome.prefix);
        res.pipe(clientRes);
        return;
      }
      if (outcome.reason === 'client-aborted') return;
      if (attempt >= MAX_RETRIES) {
        // 弹尽粮绝: 返回 503 触发客户端引擎自动重发(CLAUDE_CODE_MAX_RETRIES), 而非透传空流逼用户手点 Try again
        log(`${clientReq.method} ${clientReq.url} attempts exhausted (${outcome.reason}) -> 503 for client auto-retry`);
        clientRes.writeHead(503, { 'content-type': 'application/json' });
        clientRes.end(JSON.stringify({ type: 'error', error: { type: 'overloaded_error', message: 'Relay: upstream dead channels exhausted all retry attempts' } }));
        return;
      }
      log(`${clientReq.method} ${clientReq.url} attempt=${attempt} 200-empty(${outcome.reason}) -> retry`);
      await new Promise((r) => setTimeout(r, backoffMs(attempt)));
    }
  });
});

server.listen(LISTEN_PORT, '127.0.0.1', () => log(`ccp-relay listening on 127.0.0.1:${LISTEN_PORT} -> ${UPSTREAM_HOST}:${UPSTREAM_PORT}`));
```

### 3. 配置开机自启（登录即后台运行，无窗口）

新建 `C:\Users\<你>\.claude-tools\start-relay.vbs`（注意把 `<你>` 换成实际用户名，或直接用 `%USERPROFILE%` 对应的绝对路径）：

```vbs
CreateObject("Wscript.Shell").Run """C:\Program Files\nodejs\node.exe"" ""C:\Users\<你>\.claude-tools\ccp-relay.js""", 0, False
```

把它复制一份到用户启动文件夹（资源管理器地址栏输入 `shell:startup` 回车即到）：

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ccp-retry-relay.vbs
```

### 4. 首次启动并验证中继

手动启动：双击 `start-relay.vbs`；或前台跑便于看日志：

```bash
node "C:\Users\<你>\.claude-tools\ccp-relay.js"
```

验证（发一发真实流式小请求）：

```bash
curl -s -N -X POST http://127.0.0.1:15722/v1/messages -H "content-type: application/json" -d "{\"model\":\"claude-fable-5\",\"max_tokens\":50,\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"reply with: RELAY_OK\"}]}"
```

预期：返回 `event: message_start` 开头的 SSE，且 `relay.log` 里出现 `model claude-fable-5 -> glm-5.3-flash` 和 `ok stream` 字样。

### 5. 把桌面应用改道到中继

编辑 `%LOCALAPPDATA%\Claude-3p\configLibrary\_meta.json` 中 appliedId 指向的那个条目 JSON，把网关地址改为中继：

```json
"inferenceGatewayBaseUrl": "http://127.0.0.1:15722"
```

其余字段不动。然后**完全退出并重启 Claude 桌面应用**（该配置只在启动时读取）。

### 6. 验收

- 正常使用若干轮：不再弹「Stream ended」；偶尔某轮响应慢一两秒 = 中继在幕后重发，属正常。
- 看 `C:\Users\<你>\.claude-tools\relay.log`：每次请求的模型映射、第几次尝试、成败全有记录；`retry` 行数就是「以前你需要点 Try again 的次数」。

### 7. 故障速查

| 症状 | 处理 |
|------|------|
| 中继进程不在 | `netstat -ano | findstr 15722` 无 LISTENING → 双击 `start-relay.vbs` |
| 桌面报连接拒绝 | 中继没起，同上 |
| relay.log 大量 retry | 上游死通道率高，属中继正常消化；若连 5 发全死仍报错，属上游全面故障，等恢复 |
| `count_tokens` 404 | cloudprime 不支持该端点，无害，客户端自动降级估算 |

## 五、注意事项

- **Key 安全**：ccp-relay.js 含明文 Key，仅留本机，严禁提交仓库或外传。
- **与 cc-switch 的关系**：部署本方案后桌面不再依赖 cc-switch（可关/卸）；终端 CLI 若仍走 cc-switch 则继续开着，或把 CLI 的 `ANTHROPIC_BASE_URL` 也指向 `http://127.0.0.1:15722` 后彻底退役 cc-switch。注意 cc-switch 的界面操作可能覆写 settings.json。
- **已知残留**：上游非流式路径 100% 死，中继目前对非流式请求只透传（客户端在层 1 已关掉降级，正常使用不会走到）；彻底解法是中继把 stream:false 转成流式发上游再组装回 JSON，暂未实现。
- 模型映射表（claude-* → glm-*）在脚本头部 `MODEL_MAP`，按需自行调整。
