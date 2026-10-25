---
name: wecom-notify-channel
description: 企微自建应用通知外推已落地(notify_users 第三条腿):配置键/掩码/队列worker/双线出口可信IP坑
metadata:
  node_type: memory
  type: project
  originSessionId: c59955d9-24d4-4a7f-90d5-8943adb3ca0a
  modified: 2026-09-30T09:27:11.936Z
---

09-30 落地企业微信通知外推:`notify_users()` 落库+WS 之外加第三条腿推企微自建应用。架构:services/wecom_client.py(token 模块级缓存过期前5min刷新+失效重试一次;daemon 线程+queue.Queue 异步发,业务端点只入队)+ notification_hub._relay_wecom(按 feed_users.wecom_userid 映射,没配的人静默跳过)+ system_config「notify.wecom」={enabled,corpid,agentid,secret}(secret write-only 掩码,沿用 llm_config 套路,api/system_config.py _mask_wecom_value)+ 测试端点 POST /api/system-config/notify.wecom/test(admin)。

**Why:** 用户真实企业(ww2ef7a300f2001aaf, agentid 2);secret 已入 DB,API 永不回明文。

**How to apply:** ⚠️企微 2022+ 门槛:配可信IP前必须先有可信域名**或**接收消息回调URL(都要公网触达)——用户被卡在这;回调握手端点需 AES 库(venv 两样都没有,装 pycryptodome 才能写)。已加**群机器人 webhook 腿**(notify.wecom.webhook_url,零门槛,中继里配了就广播;URL 含 key 已进掩码字段)。群广播格式(09-30 两轮迭代定稿):任务类=**「@姓名 有新任务：XX · 节点」**(title 前缀「你有新任务：」replace 掉),其余类型=原文+「（通知：姓名）」脚注;收件人配了 wecom_userid 才走 mentioned_list 真@高亮,未配只是文字@。⚠️角色空缺发现:在职用户 cost 角色 0 人(te 只有学同/quote 只有 kayfly),成本节点不指派时流程照样推进但零通知(静默黑洞),指派非 cost 角色 409;离线有「权限测试-成本」测试号。⚠️新版企微「群机器人」已改名**「消息推送」**:入口=群聊右上角⋯→消息推送/群机器人;外部群(含微信用户)不支持、仅群主可管理的群只有群主可见、管理员后台「应用管理→消息推送」控制创建权限。⚠️用户家宽**双线出口**(电信 180.159.124.91 + 移动 139.226.97.196 路由分流),可信IP两个都得填,漏一个 60020 时通时断;IP 变了要再补。联调用 send_text 直发脚本或 test 端点;正式路径要后端重启加载新代码。前端:用户管理页「企微ID」列内联编辑(blur/回车保存)。todo: 企微卡片跳转链接(需公网,未做)。
