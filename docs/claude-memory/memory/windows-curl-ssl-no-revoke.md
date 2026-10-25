---
name: windows-curl-ssl-no-revoke
description: "Windows Git Bash 的 curl 走 schannel,HTTPS 因 CRYPT_E_REVOCATION_OFFLINE 失败,需加 --ssl-no-revoke;Python requests/certifi 不受影响"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 0aa265ad-5de4-4f99-a706-563646f639bb
  modified: 2026-07-30T16:49:39.649Z
---

在 Windows Git Bash 里用 `curl` 调 HTTPS 接口会报:

```
curl: (35) schannel: next InitializeSecurityContext failed:
CRYPT_E_REVOCATION_OFFLINE (0x80092013)
```

原因:Windows 版 curl 默认用 schannel 做 TLS,会做证书吊销检查(OCSP/CRL),本机网络(代理/墙)连不上吊销服务器 → 整个请求失败。**不是 key 或对方服务的问题。**

**How to apply:**
- Bash 里的 `curl` HTTPS 调用一律加 `--ssl-no-revoke`(或换 `--tls-max` 等也行,但 `--ssl-no-revoke` 最直接)。
- 验证过:Firecrawl REST API 加该参数即 HTTP 200 正常(见 [[firecrawl-skill]] 使用)。
- **Python 不受影响**:后端用 `requests` / Firecrawl Python SDK 走的是 `certifi` 证书包,不做 schannel 吊销检查,无需特殊处理。所以这个坑只在 Bash/curl 手动调试时出现。

**Why:** 第一次调 Firecrawl API 直接撞这个错,容易误判成 key 失效或网络不通;实际加一个参数就好。
