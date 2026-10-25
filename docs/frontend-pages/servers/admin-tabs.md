# 服务器管理 Tab (Admin Tabs)

> 最后更新：2026-10-04（六 tab 视觉整改：导航=左侧 rail 与解决方案页 StrategyPortal.side **同款配方**（216px / 右侧 hairline / sticky `--cpq-sticky-top` 全高 / 品牌行「CPQ · 服务器管理」/ hover w6 底 / 激活=主色 12% color-mix 底，手机 ≤768 折横滚条）；**六 tab 全部摘掉面板壳**，玻璃只留卡片/缩略图本体（图纸配置为基准状态），区块层级=标题 17px/700+留白；版心对齐 1180；**切区滚动归顶**（watch adminTab → .main-scroll 归零，修 v-show 滚动残留：短区钳位/回切跳深处）；**料号库分类栏 sticky 跟随**（`top: sticky-top+12`，魔法数 130px 改 `100vh - sticky-top - 24`）；**rail sticky 修复**（原 `align-items:flex-start` 使布局塌成内容高 + rail 固定高 → 短 tab rail 被父容器推出视口；改 `max-height` + rail 自身 `align-self:flex-start`，短 tab 页面无滚动、长 tab rail 吸 `--cpq-sticky-top`）。此前一轮：面板头 17px/700、`sa-table` 表格质感（styles/server-admin.css）、`seg2` 分段筛选、卡片圆角 16+hover 蓝边、系列管理卡片化、料号弹窗彩条删除、分类抽屉玻璃化、modal max-width 兜底。结构与功能零改动；原型=server-admin-restyle.html（已同步去框）

## 功能概述

服务器管理后台（`/servers/admin`，宿主组件 `ServerAdminPage.vue`）下各 Tab 的管理界面（机型管理 / 产品系列 / 基准配置 / 料号库 / 图纸配置 / 门户设置）。入口与路由见 [server-admin.md](server-admin.md)。

> 配件适配 Tab 已于 2026-08-03 移除：specs.chassis「适用系列」声明未被任何装配逻辑消费，纯参考视图冗余（料号库/基准配置/兼容性规则已覆盖装配约束）。

## Tab 1: 料号库 (PartsLibrary)

### 功能
- 配件列表（卡片/表格视图切换）
- 分类筛选（两级：section + category）
- 新增/编辑/删除配件
- 编辑表单字段：料号 PN / 名称 / **规格**（自由文本规格串，如 `PCBA_3.5''_Triple-mode`）/ **说明**（人话用途介绍，给不熟悉的同事看）/ 部段 / 类别 / 单价 / 扩展属性
- 扩展属性（schema-driven：enum-single, enum-multi, free-tags, number, text）—— 结构化规格存 `specs` JSONB（wattage/tdp/io_slot/chassis…）
- 按 section/category/chassis/series 筛选
- 搜索（料号/名称/规格/说明）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表（筛选+搜索） |
| GET | `/api/parts/sections` | `partsApi.sections` | 段列表 |
| GET | `/api/parts/categories` | `partsApi.categories` | 分类列表 |
| POST | `/api/parts` | `partsApi.create` | 创建配件 |
| PUT | `/api/parts/{pn}` | `partsApi.update` | 更新配件 |
| DELETE | `/api/parts/{pn}` | `partsApi.delete` | 删除配件 |

### 数据库表
| Schema | 表 |
|--------|-----|
| `l6` | `parts_master` |
| `l6` | `part_sections` |
| `kp` | `kp_categories` |
| `kp` | `kp_parts` |
| `kp` | `kp_part_specs` |

---

## Tab 2: 基准配置 (BaseConfigBuilder + BomTemplateManager)

### BaseConfigBuilder 功能
- 基准配置列表
- 快速创建基准配置
- 跳转编辑器（→ `/servers/base-config/:id`）
- 展示：名称、系列、机箱形态、盘位、料件数、总价

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/base-configs` | `baseConfigApi.list` | 基准配置列表 |
| DELETE | `/api/base-configs/{id}` | `baseConfigApi.delete` | 删除基准配置 |

### BomTemplateManager 功能
- BOM 模板列表
- 创建/编辑/删除 BOM 模板
- **行骨架 + 逐行可选 rule（2026-09-15 三轮定稿）**：模板行配 `type/label/slot/mode` + 顺序，另可选 `rule`（逐行完整覆盖类型默认——省略 = 跟随类型默认，零配置即合理；填了 = 该行完全按自己的规则求值）
- 规则唯一权威：前端 `bomRuleEngine.TYPE_RULES` + 后端 `bom_template_eval._TYPE_RULES`（同口径镜像，`ruleForRow`/`_rule_for_row` 逐行 rule 优先）；类型默认特殊分支：OCP 槽行 qty 跟实际选配走（未选→整行隐藏）、fan 兜底数量跟机箱形态走（2U=6/4U=12）
- **取值方式可读行内 v3（2026-09-19，v2 行内直编表因凌乱打回重做）**：每行取值方式显示为**一句可读文字**（`srcLabel` 把生效规则翻成人话，如 FAN 行 `料号字段[fan]·name｜数量 跟[fan]件数｜兜底 固定 系统风扇 / 固定 6`；cable 行 `SATA 每8盘1组 · SAS 每8盘1组 · NVMe 每2盘1组｜恒 1 组｜9361 SATA cable*1、NVMe cable*2`——示例直接跑引擎 `cableSegments` 同口径实算），零点击即可看到全部生效值；点击行内文字（尾带 ✎）展开该行编辑面板 `.tr-edit`（`editUid` 单开：描述/数量左右并排，cable 三件套通栏），编辑完成点别行自动收起。**机制不变**：显示读「生效规则」（`srcAt`→`ruleForRow`），任一格改动才物化整条 rule（`touch`），物化后与类型默认 JSON 深度相等即自动撤销（`commit`）——改回默认值=自动解除自定义。自定义行左侧蓝边+操作列 `↺` 恢复默认；模板串示例随输入实时变。**v2→v3 教训：常驻可见的应该是「值」不是「控件」——零点击可见 ≠ 编辑控件常驻**（v2 描述/数量列常驻 8-10 个控件、行高参差=凌乱主因）
- **Cable 行（2026-09-17 用户定调重做）**：单行汇总、qty 恒 1（线缆整体一组），描述按盘型分段写各自组数——数量 = ⌈盘数/分组⌉（默认 SATA/SAS 每 8 盘 1 组、NVMe 每 2 盘 1 组），SATA/SAS 文案带 RAID 卡型号前缀（如 `9361 SATA cable*4`，无 RAID 自动去前缀），NVMe 直接写（`NVMe cable*4`）；文案模板占位符 `${raid_model}`/`${n}`(组数)/`${count}`(盘数) 在取值方式展开面板（cable 三件套通栏）逐类编辑（盘类型×分组×模板三小行，`dispKinds`/`setCable`，老形状缺键用默认补齐），没盘的类型自动不出现、全没盘整行隐藏。求值在 `bomRuleEngine.cableSegments`（后端 `_cable_segments` 镜像），live 变量 `raid_model`/`sata_count`/`sas_count`（报价页 Workspace.kpSummaryFor 提取 RAID 型号）
- **模板拼装行编辑增强（2026-09-17 方案A）**：描述来源为「变量拼接」的行（前置背板、自定义后的电源行等），模板输入旁「＋变量」中文下拉（`盘位数 ${bays}`）点选即插入占位符；输入框下示例随输入实时变（演示机型渲染，缺变量显示 ？＝真实场景留空手填），模板用到 `${bp_type_desc}` 时附一句背板类型跟盘走（配了 NVMe → NVMe/SATA/SAS 三模，否则 SATA/SAS）。纯编辑器 UI（`BomTemplateManager.tplExample/insertTplVar/VAR_MENU`），引擎/后端零改动
- 模板关联到基准配置（bom_template_id）
- **表格列（2026-09-19 可读行内 v3）**：拖拽/#/左栏标签/类型/取值方式/操作——取值方式列常显生效值一句可读文字（点行内文字展开编辑）；槽位/形态小下拉收在类型格（仅 io_slot/rear_summary 行）。**添加行=表格尾行**虚线「＋ 选类型添加行」下拉（学新增入口尾卡范式，原表外「+ 添加行」按钮已删）
- 拖拽排序行
- 查看模板使用情况（有多少 base_config 在用）
- **实时预览（所见即所算）**：机型上下文（2U/24盘位等）为演示 vars；零件名从料号库拉真件（按分级匹配每类取一件，如 fan → 6056高性能热插拔风扇），接口失败退回演示值；每行只在异常时标胶囊（兜底/留空，`evalBomContext` 的 descSrc/qtySrc 取最差——命中不标，2026-09-18 删「计算」胶囊）
- **底盘件分级匹配**（前后端两引擎同口径，前端 `bomRuleEngine.findBomPart` / 后端 `bom_template_eval._find_part`）：① category 精确/子串/别名命中优先 ② 找不到才退 name 子串——防「风扇背板转接线」（name 含"风扇"的线缆）蹭进 FAN 行；别名表 = `system_config.bom_category_aliases`（⚙️ 品别名入口维护）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/bom-templates` | `bomTemplateApi.list` | BOM 模板列表 |
| GET | `/api/bom-templates/{id}` | `bomTemplateApi.get` | 获取模板详情 |
| GET | `/api/bom-templates/for-base-config/{id}` | `bomTemplateApi.getForBaseConfig` | 获取基准配置关联的模板 |
| GET | `/api/bom-templates/{id}/usage` | — | 统计模板使用情况 |
| POST | `/api/bom-templates` | `bomTemplateApi.create` | 创建 BOM 模板 |
| PUT | `/api/bom-templates/{id}` | `bomTemplateApi.update` | 更新 BOM 模板 |
| DELETE | `/api/bom-templates/{id}` | `bomTemplateApi.delete` | 删除 BOM 模板 |

### 数据库表
| Schema | 表 |
|--------|-----|
| `l6` | `base_configs` |
| `l6` | `base_config_parts` |
| `l6` | `bom_templates`（rows JSONB 存行骨架 type/label/slot/mode） |

---

## Tab 3: 机型管理 (ModelManager)

### 功能
- 服务器类型管理（CRUD）
- 机型管理：**列表卡片 + 删除**；新建/编辑跳独立编辑页 `ModelEditorPage`（→ `/servers/models/:id/edit`、`/new`），不再用 modal（详见 [model-editor.md](model-editor.md)）
- 类型-机型层级关系
- 机型关联基准配置
- 卡片网格展示：生命周期 chip、下架机型「已下架」chip（左上角，`show-publish`）、主图、形态/盘位/系列（继承自 base_config）、基准配置名
- 生命周期状态（new/active/eol/discontinued）
- 机型继承技术规格（form/bays/series）从关联的基准配置
- 图片上传支持（主图）
- 机型资料 PDF 上传（编辑页「产品资料」节：仅 PDF ≤20MB，存 `product_content.docs`，保存时后端 diff GC 清文件；详情页铭牌卡「下载资料」下载，详见 [model-editor.md](model-editor.md)）
- 机型字段：name, type, lifecycle_status, image_url, **product_content**（产品化包装 JSONB：概述/应用场景/核心特性/产品规格）
- 已移除前端字段：use、description（DB 列保留）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/types` | `catalogApi.listTypes` | 类型列表 |
| POST | `/api/server-catalog/types` | `catalogApi.createType` | 创建类型 |
| GET | `/api/server-catalog/models` | `catalogApi.listModels` | 机型列表 |
| POST | `/api/server-catalog/models` | `catalogApi.createModel` | 创建机型 |
| PUT | `/api/server-catalog/models/{id}` | `catalogApi.updateModel` | 更新机型 |
| DELETE | `/api/server-catalog/models/{id}` | `catalogApi.deleteModel` | 删除机型 |
| POST | `/api/server-catalog/models/image` | — | 上传机型图片（multipart） |
| GET | `/api/server-catalog/model-image/{filename}` | — | 读取机型图片 |
| POST | `/api/server-catalog/models/docs` | `catalogApi.uploadModelDoc` | 上传机型资料 PDF（仅 .pdf ≤20MB，`?model_id=` 按机型子目录落盘） |
| GET | `/api/server-catalog/model-docs/{file_path}` | — | 读取机型资料 PDF |
| GET | `/api/base-configs` | `baseConfigApi.list` | 基准配置列表（关联选择） |

### 数据库表
| Schema | 表 |
|--------|-----|
| `l6` | `server_types` |
| `l6` | `server_models` |
| `l6` | `base_configs` |

---

## Tab 4: 门户设置 (PortalBannerSettings)

### 功能
- 服务器门户（`/servers`）banner 配置：标题 + 轮播图（每张图可配独立副标题）
- 标题留空 = 门户回落内置默认标题；**全局副标题已移除**——副标题只随图走，缩略图下方输入框按图配置，门户随轮播切换展示，留空不显示
- 轮播图：多张上传（`/models/image?type=portal-banner`，落**内容寻址图片池** `storage/model-images/`：文件名=原名+内容 sha256 前 16 位，同图重传/跨机型共用都是同一份文件），缩略图行内复制链接/前移/后移/删除，首张为主图；不传图时门户 banner 用内置银河星空场景
- **按链接添加**：粘贴本站 `/api/server-catalog/model-image/...` 或外部 http 图直链加入轮播
- **已上传图库**：列出本站图片池全量文件（`storage/model-images/` 递归，含机型主图/场景图历史子目录，mtime 倒序），点图加入轮播、角标复制链接、标注「已在轮播」；复制出的链接为补全 origin 的绝对 URL
- 保存写 `system_config.server_portal_banner`（JSON：`title` / `images: [{url, subtitle}]`；后端兼容存量纯字符串 images 项与旧全局 subtitle，读时自动归一化丢弃），刷新门户生效；移出轮播且全库无引用的图片文件保存时自动删除

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/portal-banner` | `catalogApi.getPortalBanner` | 读 banner 配置 |
| PUT | `/api/server-catalog/portal-banner` | `catalogApi.savePortalBanner` | 保存 banner 配置（require_admin） |
| GET | `/api/server-catalog/portal-banner/images` | — | 本站图片池列表（mtime 倒序） |
| POST | `/api/server-catalog/models/image?type=portal-banner` | — | 上传 banner 轮播图 |

### 数据库表
| Schema | 表 |
|--------|-----|
| `rules` | `system_config`（key=`server_portal_banner`） |
