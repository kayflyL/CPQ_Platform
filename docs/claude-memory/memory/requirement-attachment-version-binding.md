---
name: requirement-attachment-version-binding
description: "需求单内嵌附件区:附件钉需求单版本(requirement_version),NULL=散件合并显示,删草稿先解绑;徽标溢出=换行不滑动"
metadata:
  node_type: memory
  type: project
  originSessionId: 53a1d8a0-346c-442f-b135-ac766a37d3e0
  modified: 2026-10-13T07:28:08.361Z
---

需求单内嵌附件区(2026-10-13 落地,原型 docs/prototypes/需求单-内嵌附件区-原型.html 定稿):

- 附件绑定 = `opportunity_attachments.requirement_version`(category=lead_requirement);**草稿提交只翻 status、版本号不变**,绑定天然稳定,无需重指
- **版本号按 max(version)+1 分配,草稿删除后会复用** → 删草稿必须先解绑(portal.py delete_requirement_draft → feed_repo.unbind_requirement_version 置 NULL);不解绑会挂到未来同名草稿
- NULL=未归版散件:存量旧附件(不迁移)+ 新建草稿未落库时的上传;弹窗里 version 匹配或 NULL 一并降级合并显示
- 附件**不进 AI 需求理解**(用户定调),只做登记留档与人工查阅
- UI:RequirementAttachmentChips 徽标条,文件名常显截断(hover 只放元信息——触屏无 hover);**溢出=换行,不做横向滑动**(滑动藏件名);宿主=OpportunityProcessBoard 需求单 modal,工作台卡头「上传附件」已移除
- 只读态(已提交版本)仅预览不可传/删

**Why:** 绑定粒度是本次讨论的核心取舍(商机级散件→版本级),解绑时机由版本复用机制倒逼。
**How to apply:** 碰需求单/附件/归档先看;改版本分配逻辑时记得解绑副作用;同类"附件钉实体版本"需求(quotation 已有 quotation_id 先例)照此模式。相关 [[collab-flow-02-business-detail]] [[mobile-adaptation-pattern]]
