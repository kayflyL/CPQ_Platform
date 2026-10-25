# Project Memory

## 前端与视觉

- [前端设计规范四层体系](design-spec-tokens.md) — tokens.css新增--cpq-space-1..6+字阶xl/2xl/3xl+圆角v3(xs2/sm4/md6/lg8/xl12/full,全站1060处已归档,border-radius禁写px字面);权威顺序=tokens(值)→Frontend_Style_Guide.md(材质层)→docs/设计规范.md(用法)→prototypes/设计规范.html(样张);新代码必须token,存量绞杀式;碰布局/间距/圆角先看
- [宣传页拟真复刻定调](promo-realistic-replica.md) — 宣传物料=1:1复刻真实UI+mock数据+标注层;逐值搬tokens.css;碰宣传物料先看
- [Glass Console 视觉系统](glass-console-system.md) — 视觉语言入口+用户偏好(Soft Glassmorphism/默认浅色/白边玻璃/马卡龙语义色)
- [禁左侧彩色装饰条【铁律】](no-card-color-strips.md) — 禁左侧竖向彩条=AI味;层级靠字号字重留白,彩色只做小圆点/小徽标;复用旧组件样式先查有无彩条
- [WP 磁贴列表无圆点](wp-tile-no-bullets-typographic-hierarchy.md) — 磁贴预览禁圆点,靠字号字重透明度做层级
- [WP 磁贴圆角规范](wp-tile-corner-radius.md) — 驾驶舱手机端磁贴8px=var(--cpq-radius-md)+玻璃token
- [服务器产品链路固定暗色](server-detail-prototype.md) — 详情+目录+货架整链固定暗色;原型HTML是视觉权威;碰服务器前端页先看
- [门户形态演进:AI壳→磁贴墙](portal-ai-shell-pluggable.md) — 磁贴墙+聊天收拢全局浮动助手;门户零新AI逻辑;碰门户先看
- [工作台磁贴墙实装](workbench-tile-wall-implementation.md) — TILES注册表+todo-summary角色化端点;角色/节点键勿混;碰工作台/待办先看
- [机型详情能力点选展示](model-detail-capability-showcase.md) — 能力带=左选维度→右介绍+参数化插画;大画布必须框满物密;碰机型详情先看
- [AI推理一体机配置器](ai-infer-configurator-plan.md) — 三栏固定框架+整卡满高内滚+Glass皮肤;碰配置器/显存门禁先看
- [顶栏让位占位div铁律](sticky-clearance-spacer-pattern.md) — 让位用.scroll-clearance非padding;嵌套滚动内吸顶top:0;碰布局/吸顶先看
- [全站手机适配模式](mobile-adaptation-pattern.md) — isMobile+双抽屉/磁贴+摘要条;触屏无hover;切视口必reload
- [前端开发微坑合集](frontend-dev-gotchas.md) — scoped透传/:global/v-show多根/auto-complete/图表色/rAF饿死/信息栏输入框七坑;写前端样式交互前扫一眼
- [浏览器E2E真实写库坑](e2e-browser-live-write-gotcha.md) — 合成Enter(keyCode=13)走通antd pressEnter,直调setupState handler同效;本地企微webhook启用,测试评论会广播真群;测评论先看
- [用户/角色管理改版](user-role-ui-redesign.md) — 10-17权限编辑器=三带层(页面磁贴/字段清单/操作折叠组,删双视图,机密键确认);碰用户权限页先看

## 商机/报价/门户

- [评论流@提及](comment-mention-notify.md) — feed发评论唯一入口后端解析@名字,comment_mention通知站内+企微,无权限脱敏;旧/api/comments已删;碰评论流/提及先看
- [商机状态变更=评论流+归因字典](opportunity-result-change.md) — result-change端点原子写归因+发【状态变更】评论;原因字典system_config可管理;te角色权限已补;碰状态/跟进先看
- [商机四步流程权限审计](portal-flow-perms-audit.md) — 状态门控+行菜单转交+无主居中弹窗三列网格;碰portal/feed/指派先看
- [需求单附件版本绑定](requirement-attachment-version-binding.md) — 附件钉requirement_version,NULL=散件合并,删草稿先解绑(版本号复用);溢出=换行;附件不喂AI;碰需求单/附件先看
- [报价外发审批门](quote-outbound-approval-gate.md) — 三口一闸,批准=对content_hash的外发许可改价重批,路由=调度面板approval伪节点按业务指派;闸门逻辑在services/quote_outbound_gate.py;碰报价导出/发送/审批先看
- [产出物分享](artifact-share-links.md) — ShareDialog公共组件+视角化导出(reveal机制,scheme/cost/internal,customer锁定)+免登录token下载(/api/share/*需放行);碰分享/导出/转发先看
- [商机/报价标识语义](opportunity-identity.md) — 商机靠customer_name、报价靠quotation_id唯一;碰标识/搜索先看
- [商机详情页智能化](opportunity-detail-intel.md) — 推理流+方案卡+BOM抽屉+确认转草稿;碰详情页/推理流先看
- [报价导出价格揭示机制](quote-export-reveal.md) — 五列式+质保只显示总价+L6合并格;客户版敏感列=整列物理删除非隐藏,空数据也摘列;碰导出模板先看
- [KP行价方向感知:同步vs采纳](quote-price-direction.md) — price_set_at锚点vs库价日期分流;碰报价比价/同步先看
- [报价KP行原始单价可手改](quote-kp-row-price-edit.md) — 行内编辑RMB所见即所改,USD反解;碰报价价格编辑先看
- [需求库外项匹配度分级](requirement-gap-match-grading.md) — 库外项不拦截,匹配度三态不阻塞;碰需求单录入先看
- [协作流程页面进度](collab-flow-02-business-detail.md) — 01门户+02业务详情已落地,03~06已放弃(2026-10-22定调);碰协作流程先看
- [规范字段标签来源](canonical-field-labels.md) — 权威源=init_business_fields.py种子;antd列必须dataIndex
- [写工具六件套+上传暂存+现场视图](write-tools-foundation.md) — 方案助手能办事:六写工具+聊天上传暂存跟随+ai_read现场视图(cost_sheets只有元数据!)+自然标识+记忆闭环v1;两阶段确认;碰写工具/加价/确认/上传/视图先看
- [FAE业务需求统计管线](fae-requirement-dashboard.md) — 汇总表=用户手工权威台账(6源文件仅备份,别提议重建);清洗输出目录+离线dashboard.html;2026-10-23匹配39行/待确认22/116客户不在CPQ;碰FAE统计先看

## 服务器/料号/KP库

- [配件库价门双键](parts-price-gate.md) — field.parts.price(看)复活+action.parts.price.manage(写)拆出;quote看/te-business无价;价格fail-closed灰度不豁免;新价格端点必须接线否则扫描测试挂;碰配件价格/权限/匿名可见先看
- [KP配件与derive状态](kp-parts-unification-roadmap.md) — L6件与KP件分开管理(定调别再提统一);碰KP/配件/derive先看
- [料号库与KP库区分](parts-vs-kp-distinction.md) — 料号库→l6.parts_master,KP库→kp.kp_parts;两套别混淆
- [料号库分类法](parts-section-taxonomy.md) — 大类/STEP由part_taxonomy用户可改,改名批量传播;别锁闭集
- [KP spec覆盖率](kp-spec-coverage-sparse.md) — 89%+硬盘5维100%;剩GPU/CPU国产卡手填;碰spec先看
- [KP一物多码去重](kp-dedup-tier-a.md) — 三轮287→173;报价匹配四级阶梯;嵌入召回不进热路径;碰件合并先看
- [KP导入合并范式](kp-import-merge-playbook.md) — 先转换+dry_run+价格去重,别直接导;脏数据用户拍板
- [L6机箱库过渡态](l6-chassis-legacy-flow.md) — 读_old备份表与base_configs两套表;定调止血别重构
- [L6底座能力档案](l6-baseconfig-capability-state.md) — 能力档案已回填;CRE碰不到机箱能力字段;碰base_config先看
- [OCP属网络非PCIe](ocp-is-networking-not-pcie.md) — OCP独立「网络」分段不与IO槽混;存rear['OCP']
- [后面板统一到料号库](rear-panel-unified-to-parts-master.md) — IO语义存parts_master.specs;差价靠拆PN;碰后面板先看
- [后面板选料权属](rear-panel-producer-consumer.md) — 编辑器=类型卡内选PN;配置页只调数量;defaults存PN列表
- [管理面卡片模式](admin-card-pattern.md) — 独立列表卡片+编辑modal别嵌套;基准编辑UI用户设计勿动
- [新增入口尾卡范式](add-entry-tail-card.md) — 新增=网格尾虚线「＋」卡;标题行不放「+添加」按钮
- [推导必须手填兜底](derive-must-have-manual-fallback.md) — 料号数据大量不全,推导必须可手填
- [Excel L6存bom_excel_rows](excel-l6-reference-bom-excel-rows.md) — L6仅参考存config_l6_picks;不填则丢L6
- [Excel解析表头锚定](excel-parse-rules-header-anchor.md) — 模板归属=使用位置绑定+弹窗三栏;碰excel_parser先看
- [BOM模板骨架化](bom-template-skeleton-redesign.md) — 值一句常显+点行展开编辑;常驻的是「值」非「控件」
- [BOM填充训练循环](bom-fill-training-loop.md) — extract冻结,新差异走llm_agent prompt不加regex

## AI办公室/同事

- [AI办公室3D布局](office-3d-layout-seed.md) — 种子在ai_colleagues.py但DB权威,改种子配旧坐标迁移
- [办公室3D重构计划](office3d-refactor-plan.md) — 绞杀式R0→R5拆office3d/纯TS引擎;碰Office3DCanvas先看
- [头顶件弹性锚定](office3d-elastic-head-anchor.md) — 头顶件Y实测包围盒推导禁魔法数;勿信登记height;复刻实验bake在scale前调
- [Live2D形象快照导出](l2d-snapshot-capture.md) — l2dSnapshot的rAF时机bug,修复=同帧rAF同步读WebGL
- [行为配置页V2](office-behavior-v2.md) — daily_plans区间日程;任务>作息>空闲;碰office_clock先看
- [cumora协调参考](cumora-agent-coordination-reference.md) — 浮动面板=消息中心;多房间=有名字的群线程;碰多agent协调可看
- [ChatSessionRuntime](chat-session-runtime.md) — 会话=渠道键→唯一对象多窗口共享;碰聊天/WS先看
- [同事结构化记忆](colleague-structured-memory.md) — 两级分域:私有域仅本人注入,治理面管公共域;碰员工页/记忆先看
- [AI办公室专家审计](docs/AI_OFFICE_AUDIT_20260827.md) — P0=并发锁+抽屉清理+死码;P1(run表/eval harness)已放弃(2026-10-22定调)
- [智能转接LLM判官](dispatch-llm-judge.md) — 转接只在群里;群内按名册;碰转接先看

## Skill/工作流/策略

- [工作流发起两入口](workflow-entry-arming-suggest.md) — 「+」装填模式不发占位消息+suggest_workflow一键确认卡(2026-10-15);碰工作流入口/同事聊天/launcher先看
- [配件卡自选空下拉](askcard-selfpick-race.md) — 根因=发卡先广播后落last_card的竞态(秒点409)+失败只显示小字;已修=先落库再广播+重试一次+错误行进下拉;碰自选/AskCard/card-pick先看
- [Skill树干-枝叶架构铁律](skill-tree-trunk-architecture.md) — 各归唯一DB权威源无第三层;节点五插槽+agent_fill复用;改skill先看
- [relay错误盲降级成不支持tools](relay-error-misclassified-unsupported.md) — anthropic通道瞬态错误曾静默吞整轮零trace→「本步执行失败」;已修=形状判别;查LLM断流/通道错误先看
- [需求分析skill当前态](skill-current-state-2026-09-12.md) — 权威文档指针+原生FC/9工具+规则压缩11条;碰skill先读
- [skill诊断修复史【史料】](skill-takeover-diagnosis.md) — 演进史+踩坑实录有长期价值;当前态看skill-current-state
- [Skill延迟优化](skill-latency-program.md) — 471s→368.6s根修四件套+e2e隔离跑法;碰skill延迟先看
- [需求分析工作流设计意图](requirement-skill-design-intent.md) — skill→workflow,AI=唯一大脑;碰输出/验收先看
- [需求分析双路线重构](requirement-analysis-dual-route-redesign.md) — ⚠️v9实现已整体回退,startup migrate钩子是根因
- [推断槽位必确认](inferred-slots-must-confirm.md) — 推断值必须弹确认卡;明说不问、推断必问
- [需求域规则页](requirement-rules-domain.md) — 知识化注入已实施;影子校验永不代填;碰规则页先看
- [趋势分析workflow修通](trend-workflow-second-machine.md) — 七节契约+数据范围可配;碰趋势前必看
- [策略中心全景](strategy-center.md) — pricing+selection活跃;CRE域=KP件;碰策略先看
- [bp_type迁移到CRE](bp-type-migrated-to-cre.md) — 背板判定迁CRE derive赋值规则,改即生效
- [CRE规则元数据SSOT](cre-rule-meta-ssot.md) — 文案集中constants/ruleMeta.ts;别裸写
- [可视化推理流](reasoning-flow-viz.md) — vue flow DAG+图驱动executor;P2全完成;碰推理流先看
- [推理流agent架构定调](agent-architecture-decision.md) — 确定性管道当编排器;全自治agent是反模式
- [推理流匹配增强](reasoning-match-enhanced.md) — 内存反推条数+多规格网卡+底盘件信号注入;碰推理流匹配先看
- [推理流试运行playground](reasoning-testrun.md) — 画布下内嵌输入→节点逐步高亮;simpleeval缺失已补
- [推理流migrate防膨胀gate](reasoning-flow-migrate-gate.md) — active_is_current()单点gate;加migrate必须带guard
- [反问补全机制](clarity-rebuttal-mechanism.md) — clarity_check→cond_clarity→ask_user;force_complete是per-request
- [AI路需求理解纯LLM填表](agent-understand-pure-llm.md) — llm_agent=LLM填表+确定性resolver;纯LLM抽取100%可靠

## 平台/基建/安全

- [GitHub访问通道](github-access-channels.md) — 直连被墙,git代理10809(v2rayN)进程常没开;gh-proxy.com拉整仓/jsdelivr拉单文件;碰github下载先看
- [认证+RBAC系统](auth-rbac-system.md) — JWT+角色权限+price_mask遮罩;碰API/入口先看
- [权限体系差距审计](perm-gap-audit-2026-10.md) — 174端点收口(文件服务端点白名单勿动)+AI价格绕行修通;仍开放=登录防护/密码策略/审计;碰权限/新API先看
- [价格权限按角色控制](price-access-role-control.md) — price_access默认关;新价格字段必须接price_ok门控
- [query_data只读原语](query-data-primitive.md) — 物理强制保留;工具即权限白名单
- [API密钥安全加固](api-key-security-hardening.md) — system_config鉴权+llm_config掩码+仓库零密码;碰密钥/公开仓库先看
- [企微通知外推通道](wecom-notify-channel.md) — ⚠️双线出口两个IP都要进可信IP
- [PWA手机桌面安装](pwa-mobile-install.md) — 5173 HTTP常开+5443 HTTPS门自签CA;安卓装CA才可安装,iOS直接添加;禁自动跳转;碰PWA/手机安装/证书先看
- [bat必须GBK+CRLF无chcp](bat-crlf-rule.md) — 65001下cmd中文行漂移撕碎解析是绝症,GBK+936是原生路径;改bat用python二进制;碰bat/双击脚本先查
- [规格书打印服务端PDF](spec-print-server-pdf.md) — 统一序列化DOM→print-pdf→Playwright直下;碰打印/PDF先看
- [磁盘文件命名](disk-filename-readable-naming.md) — 原始名+短UUID防孤立;excel源文件归档Feed附件表
- [直连CPQ数据库](cpq-db-direct-query.md) — config.py默认postgres/961216+SQLAlchemy;别用.env的stale URL
- [App startup](app-startup.md) — backend/.venv(uv创建,装包uv pip),Windows需-X utf8
- [部署现状内网用户级](deploy-ubuntu-single-machine.md) — 10.32.39.132 kayfly家目录,5173/5443(TLS门)/5174/5499,cron看门狗;碰部署/发版先看
- [服务器库单向合并20261016](server-db-merge-20261016.md) — 本地14商机树725行灌服务器,ALL_OK;服务器DB用户=cpq非postgres;碰数据同步/迁移先看
- [前端类型校验环境](frontend-typecheck-env.md) — 自验跑cd frontend&&npm run build;别用npx vue-tsc
- [操作微坑合集](ops-workflow-gotchas.md) — Edit长载荷掺杂质/小批量读/避免批量读写/curl --ssl-no-revoke/命令带目录五坑;执行长任务前扫一眼
- [LLM栈三合一](llm-stack-notes.md) — z.ai官方anthropic端点/reasoning思考走reasoning_content/全面在线化只留降级;碰LLM链路先看
- [cc-switch 502根因](cc-switch-502-root-causes.md) — cloudprime限流429;解法提额/failover/少开并行
- [Firecrawl两役](firecrawl-spec-extract-poc.md) — spec抽取全链路通一次~5credits;价格爬取京东被挡淘宝可爬,实时价别依赖爬JD
- [img2threejs已装](img2threejs-installed.md) — 图片→Three.js模型;先跑forge/next.py
- [Claude-3p环境与skill位](claude-3p-environment.md) — 用户自装skill在~/.claude/skills/;需放<根>/<name>/SKILL.md
- [对外宣传页](promo-landing-page.md) — public/promo/index.html单文件;defer内联脚本包DOMContentLoaded
- [星河首页镜像基线](galaxy-mirror-baseline.md) — 线上=public/galaxy;只动>显示文本<;缺ani-tiles.exr卡93%
- [文档同步三规则](docs-sync-rules.md) — 改docs刷最后更新日期/改前端页同步docs+README/先查frontend-pages再查代码

## 用户定调/协作方式

- [原型=规格书](prototype-is-the-spec.md) — 原型确认后不许自砍范围;做不了的先说清拍板
- [UI精简别加模式](ui-simplify-dont-add-modes.md) — 嫌乱=要精简不是加功能;别加并列模式
- [系统性梳理而非打地鼠](systematic-cleanup-not-whackamole.md) — 修单点主动扫同类一并改
- [别在补丁上打补丁](no-patch-on-patch.md) — 修bug同步清理关联冗余;自问有无两段代码做同一件事
- [大任务一次授权推进](autonomy-large-tasks.md) — 别每步求同意,推进到结果再汇报;高危动作可逆兜底
- [自验证别踢给用户](feedback-verify-yourself-dont-bounce-user.md) — 反复修不好自己起dev server抓证据
- [视觉改动让用户先确认](visual-changes-let-user-confirm-first.md) — CSS/布局改完说一声就停,别主动驱动浏览器
- [改UI须主动审整页](proactive-page-coherence-audit.md) — 改某控件主动看整页合理性
- [禁令不进黑盒代码](feedback-no-instructions-in-code.md) — 指令性文字只住manual_rules,代码只许形状陈述
- [并行会话禁用git restore](no-git-restore-concurrent-sessions.md) — 回退只用Edit精确反做;脏文件=别人的在途工作
- [复现写请求会写生产库](repro-writes-hit-real-db.md) — 打写端点=真写库;先备份或走fake-repo;e2e物理清数据
- [业务事实不发明种子值](no-invented-seed-values.md) — 新表默认空+管理面录入;先问"业务事实还是技术常量"
- [节点卡单层卡头铁律](node-card-single-header.md) — 卡头=唯一标题层;RecordTable:empty算占位行
- [登录凭据位置](login-credentials-location.md) — admin密码自设无从得知;别重置密码
- [Docs vs code drift](docs-code-drift.md) — 文档滞后,引文档要核对代码
- [template_json opaque blob](template-json-opaque-blob.md) — 后端当不透明JSON存;前端加可选字段自动往返
