---
name: user-role-ui-redesign
description: 10-01/02用户角色管理改版全部落地：V1抽屉化+V2底版增量编辑器+分页(20/页,hideOnSinglePage)+排序(姓名/最近活跃)+添加成员弹窗搜索；文档已同步 docs/frontend-pages/settings/users-roles.md；原型在 frontend/public/prototypes/
metadata:
  node_type: memory
  type: project
  originSessionId: c0f7a6a2-58e3-4720-b03a-1f1a8510b0f1
  modified: 2026-10-16T13:04:23.873Z
---

---
name: user-role-ui-redesign
description: 10-01抽屉化+底版增量编辑器；10-17权限编辑器再改三带层(页面磁贴/字段清单/操作折叠组,删列表+网格双视图,机密键确认,生效提示,两Tab打通)；碰用户权限页先看
metadata:
  node_type: memory
  type: project
  originSessionId: c0f7a6a2-58e3-4720-b03a-1f1a8510b0f1
  modified: 2026-10-17T12:00:00.000Z
---

**2026-10-17 三带层再改版（规格=docs/prototypes/权限磁贴墙-原型.html v3，用户拍板"执行"）**：权限编辑器从「列表/网格双视图」整体换为**层优先三带**——一带页面磁贴（page.\* 按域聚合，单页域=贴头大开关，商机线索/设置多页域=贴内逐行；关了=导航都不出现）、二带字段清单（6 键，域前缀+FIELD_DESC 说明+机密徽）、三带操作折叠组（按域默认收起+首组展开，组头已开 N/M+整组批量开关，增量绿字/底版划掉）。**列表+网格视图及 CSS 全删**（perm-cat/perm-item/view-toggle/grid/dchip 家族），PERM_CATS/catGroups/gridRows/ACT_ORDER/editorView 一并退役。

- 机密键 `CONFIDENTIAL_KEYS`=价格四键（quote.price/opportunity.quote_price/parts.price/parts.price.manage）：onToggle/onToggleGroup 勾开弹 Modal.confirm 带影响成员数，取消不改状态。
- 生效语义：footer「保存后 · N 名成员需刷新页面生效」+saveRole 成功提示同文案（旧「即时生效」是错的）。
- 两 Tab 打通：角色表成员列=头像堆叠（usersByRole）；用户表角色徽章 .role-link 点击 openRoleOf 直达角色编辑。
- 反 AI 味自查依据=impeccable.style/slop：去破折号文案、边框投影二选一、字段带用清单不用卡片墙、无悬浮位移。
- 坑：**openEditRole 曾漏加 resetOpenGroups()**（只加了 create/copy 两入口）——三入口都要重置折叠态；预览验证可铸 admin token 写 localStorage['cpq_auth_token'] 直接看真页（见下核对方式）。

**2026-10-01 底版增量改版（仍有效）**：用户管理 tab=状态过滤+搜索+行点击用户详情抽屉（460 宽:kv+企微行内编辑+角色下拉+Danger Zone）；角色 tab=行点击抽屉+成员数蓝链+⋯；抽屉 1080 双栏双 tab=权限配置/已授权成员；底版机制(baseChoices/autoBaseFor 重叠率≥0.5/换底版二选一)、diff computed、SHORT_LABELS 短标签表、侧栏预览、复制角色；后端 feed_users.last_login_at。

**核对方式（照此复验）**：后端铸 admin token（create_access_token）→preview 注入 localStorage→/settings/users→截图对照；坑=①两 pane v-show 同 DOM,行选择器必须 offsetParent 过滤 ②HMR 重载重置 tab ③Vue 渲染异步,click 后同步读 class 误导 ④业务角色 DB 实际权限≠种子（用户改过），diff/autoBase 跟随 DB 是正确行为 ⑤npx vite build 看 TS6133 真因。临时 token 只在预览浏览器,不入库。

**Why:** 用户先嫌角色管理不舒服（10-01 抽屉化解决）；再嫌权限编辑器「字密+没有页面/字段权限分组」——诊断=域优先把三层塞进磁贴字密、层优先才对（10-17）；再嫌 AI 味（impeccable.style/slop 清单逐条除味）。

**How to apply:** 改此页先看原型 v3 标注；权限中文标签用 DB 目录 name（[[canonical-field-labels]]）；新权限键自动进三带（group+module 驱动），机密新键要加进 CONFIDENTIAL_KEYS。关联 [[glass-console-system]] [[auth-rbac-system]] [[perm-gap-audit-2026-10]] [[parts-price-gate]]。
