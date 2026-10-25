---
name: opportunity-result-change
description: 商机状态变更唯一路径=result-change 端点;必填一句话+丢标原因字典;审计即评论流
metadata:
  node_type: memory
  type: project
  originSessionId: 9d799f3e-3da0-43c2-9264-76c861df4b47
  modified: 2026-10-12T09:25:28.684Z
---

商机状态变更(2026-10-12 批准实施):头部下拉只选目标,确认走 `POST /opportunities/{id}/result-change`(opportunities.py),原子完成两件事——extra_fields 写 `loss_reason_keys(调研表式多选勾选)/loss_note/result_changed_at`(改回 pending/won 清空归因)+ 向协作动态发 kind=comment 的【状态变更】评论(首行 旧→新·原因,次行=用户一句话)。跟进记录=右栏评论栏,无独立表(用户拍板:不建 followups 表、不做阶段里程碑、不做左栏管线)。

丢标原因字典:system_config key `opportunity.loss_reasons` = `[{key,label,enabled}]`,种子 10 项源自 FAE 进度表真实归因( startup.py `_DEFAULT_LOSS_REASONS`,幂等只补缺);管理入口在弹窗内(page.settings.users 门控),禁用不删、删除后历史回退显示 key。商机存 key 不存文案。

te 角色(技术FAE)曾缺 `action.opportunity.result` 导致改不了状态——已补进 role_repo `_DEFAULT_ROLES`,靠 `seed_missing_defaults` 启动自动补种,新权限下发走种子不走手改库。

**Why:** 用户拍板"评论即跟进+状态变更有凭据",放弃重设计(摘要条/抽屉/阶段管线均被否);统计需求(原因分布/成单周期/超期)数据侧已预留(extra_fields jsonb + 评论首行可 grep),报表后做。

**How to apply:** 碰商机状态/跟进/归因先看本条;列表页 OpportunityList 内联切状态仍走旧 update_meta 路径(绕过必填一句话),收口待用户拍板;前端组件 `ResultChangeModal.vue`,文档 docs/frontend-pages/opportunities/detail.md。相关:[[opportunity-identity]] [[portal-flow-perms-audit]]
