---
name: pwa-mobile-install
description: "PWA 桌面安装:5173 HTTP 常开 + 5443 HTTPS 门(自签CA);安卓装CA后Chrome安装,iOS 直接添加;碰 PWA/手机安装/证书先看"
metadata:
  node_type: memory
  type: project
  originSessionId: 1882bd78-581e-4a4e-9105-392afc57a92f
  modified: 2026-10-10T16:05:56.468Z
---

手机「添加到桌面」方案(2026-10-10 落地):前端有 PWA 清单(`public/manifest.webmanifest` + `public/icons/` 四张位图)和引导页 `public/install-help.html`。**两个门**:5173 HTTP 永远保留(老书签 + 证书分发),web.js 加开 5443 HTTPS 门(`TLS_PORT/TLS_CERT/TLS_KEY` 环境变量,start.sh 传入,证书缺了自动降级纯 HTTP)。安卓 Chrome 只在 HTTPS 才给「安装应用」,所以安卓必须:装 CA 证书(一次性,`/cpq-ca.crt` 路由下载,服务器 `bash ~/cpq/make_certs.sh` 生成,CA 10 年复用则换证书不用重装手机)→ 彻底重启 Chrome → 从 5443 安装。iOS 不用证书,Safari 分享→添加到主屏幕即全屏。

**Why:** 一个端口只能一种协议,HTTPS 无法与 HTTP 共用 5443/5173;服务器无法探测手机装没装证书,所以**禁止做 5173→5443 自动跳转**(会把没装证书的人推进警告页);安装出的 App 入口=安装那一刻的地址。

**How to apply:** 图标源是 favicon.svg(playwright 渲染,180/192/512+maskable,iOS 不认 SVG);独立模式下 iOS 状态栏浮在页面上——`DefaultLayout` 的 `.site-header` padding-top 与 `--cpq-header-clearance/--cpq-sticky-top` 都已加 `env(safe-area-inset-top)`,浏览器模式为 0 零影响;`--cpq-header-clearance` 在 DefaultLayout 定义全站几十处消费,改让位高度只动那一处。发版火车(一键更新.bat)会带 web.js/start.sh/make_certs.sh/update.sh 并重启前端(1~2 秒瞬断);update.sh 末尾有 frontend-tls 自检。微信内置浏览器装不了 PWA,要引导「在浏览器打开」。**上线状态(2026-10-10 深夜):已全链路打通**——证书已生成在服务器 ~/cpq/certs/,5443 经真 CA 链验证 200,manifest/icons/引导页双门全通。踩过的坑:update.sh 只认 dist.tgz/backend.tgz 包名(曾有 cpq_dist.tgz 错位,bat 从未真正发过版);start.sh 的 NODE_BIN 是模板占位已加自愈;发版 bat 曾因 chcp 65001 中文行漂移整体碎裂,见 [[bat-crlf-rule]]。相关:[[deploy-ubuntu-single-machine]]、[[mobile-adaptation-pattern]]。
