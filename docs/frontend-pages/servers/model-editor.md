# 机型产品化包装编辑页 (ModelEditorPage)

> 最后更新：2026-09-30（新增「产品资料」PDF 上传节：存 product_content.docs，保存时后端 diff GC 清文件）

## 功能概述

机型的产品化包装编辑器，单栏流式布局。顶部操作条（返回/取消/保存）**sticky 吸顶**（`top:8px` + 阴影，页面长滚动中随时可保存）。承载机型基本信息 + 面向客户的产品内容，新建/编辑共用同一组件。**产品内容编辑结构与详情页展示顺序一致**（一句话定位 → 概述 → 价值亮点 → 能力板块 → 场景适配 → 完整技术规格），每块标注对应详情页哪个区块。

### 核心功能
1. **顶栏**：返回 / 标题（新建|编辑）/ 保存
2. **基本信息 + 关联基准配置（一对多·配置变体）**：**一行四字段**（机型名/类型/生命周期/是否上架开关——下架后服务器页机型目录不展示，管理面/报价/推理流照旧可见）；配置变体卡片网格——每张卡片 设为主配置(radio)/编辑料件(跳基准配置编辑页)/取消关联/内联编辑配置简介（`config_content`：说明+规格差异两段）；「＋」卡片打开选择面板，列出未归属配置、点选即关联。**新建机型保存后留页**才能关联配置（关联需机型 id）
3. **产品主图**：本地上传（走 `/models/image`）或粘贴 URL，带缩略图预览
4. **产品资料**（PDF，`product_content.docs`）：详情页铭牌卡「下载资料」入口的数据源。文件列表行（名称/大小/删除 popconfirm）+「本地上传」（`a-upload :before-upload` 范式，仅 PDF ≤20MB，前端后端双校验）；上传即 push 进本地 docs 随机型保存落库（**新建机型无 id 也可先传**，保存时绑定）；**删除只改本地列表，保存后由后端 diff GC 清文件**（与图片池同语义）
5. **产品内容**（结构化分块，存 `product_content` JSONB，与详情页逐段镜像）：
   - **一句话定位**（tagline）：详情页铭牌副标题，15 字左右
   - **产品概述**：一段话（textarea）
   - **价值亮点**（highlights）：卡片 = 短标题（180px）+ 一句话，**两列网格**，尾虚线「＋ 添加亮点」卡；详情页 ruled list
   - **能力板块**（capabilities）：可增删维度卡 = 维度名 + 英文标签 + **图标选择条**（9 个发丝线图标单选，`capIcons.ts` 注册表，选中亮酒红）+ 一句话价值（placeholder 教写收益不写参数）+ **关键数字**（值/标签可增删行，详情页右侧小字注脚，尾虚线「＋ 添加数字」小条）；卡片**双列网格**（镜像详情页一行两卡），尾虚线「＋ 添加维度」卡；标题行只留「填入六维预设」一键铺算力/扩展性/网络能力/存储/管理/可靠与运维（只补缺失维度，不覆盖已录内容）
   - **场景适配**（scenarios）：**卡片网格**（与关联配置同语言）——每卡 缩略图（点开上传/更换配图，走 `/models/image`，hover 显 ⧉ 复制图片链接补全 origin 成绝对 URL）→ **图下常驻链接输入框**（可直接粘贴本站 `/api/...` 或外部 http 直链，清空即移除配图）→ 场景名（`a-auto-complete` **跨机型联想**）+ ✕ 删卡 → 一句话 fit；网格尾虚线「＋ 添加场景」卡（空态也常驻）
   - **完整技术规格**（specs）：可增删行（规格名 + 规格值，**规格值支持换行**，textarea autosize），列表尾通栏虚线「＋ 添加规格」条；详情页沉底折叠

> 已移除字段：用途(use)、一句话简介(description)（前端不再编辑/展示，DB 列保留）；旧「核心特性 features」结构已废弃——加载时迁移成无标题亮点行，保存后不再写 `features`

### 数据流
- 新建模式（`/new`）：空表单，类型默认取第一个
- 编辑模式（`/:id`）：`getModel` 加载机型；`listModels` 收集所有机型场景名作联想源（新结构取对象 `name`，旧字符串也取）
- **旧数据迁移（加载时一次性）**：`features[{icon,text}]` → `highlights[{title:'',text}]`；scenarios `string[]` → `{name,fit,image}[]`；保存只写新结构，后端整块替换 JSONB（旧键随之消失）
- 保存：`create`/`update`；**编辑保存成功留在本页**（可继续关联配置），新建保存后 `replace` 到编辑路由；「取消/返回」才回 `/servers/admin?refresh=models`

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/models/new` | `views/server-admin/ModelEditorPage.vue` |
| `/servers/models/:modelId/edit` | `views/server-admin/ModelEditorPage.vue` |

`route.params.modelId` 为 `new` 或空 → 新建；为数字 → 编辑。

## API 端点

### 机型
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/models/{id}` | `catalogApi.getModel` | 获取机型（含 base_config + product_content） |
| GET | `/api/server-catalog/models` | `catalogApi.listModels` | 所有机型（收集场景名联想源）；`?published_only=1` 只返回上架机型（机型目录货架用） |
| POST | `/api/server-catalog/models` | `catalogApi.createModel` | 新建机型 |
| PUT | `/api/server-catalog/models/{id}` | `catalogApi.updateModel` | 更新机型（含 product_content；保存时 diff GC 清理不再被引用的图片/资料文件） |
| POST | `/api/server-catalog/models/image` | — | 上传图片（multipart；`?type=product/scenario&model_id=` 按用途+机型分类落盘，主图与场景配图共用） |
| POST | `/api/server-catalog/models/docs` | `catalogApi.uploadModelDoc` | 上传资料 PDF（multipart，仅 .pdf ≤20MB；`?model_id=` 按机型子目录落盘，缺省落根目录）→ `{name,url,size}` 存入 product_content.docs |
| GET | `/api/server-catalog/model-docs/{file_path}` | — | 读取资料 PDF（路径段防穿越 + nosniff；兼容机型子目录与根目录两种形态） |

### 关联数据
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/types` | `catalogApi.listTypes` | 类型下拉 |
| GET | `/api/base-configs` | `baseConfigApi.list` | 基准配置下拉（继承参数 + 名称展示） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_models` | 机型主表（name, server_type_id, base_config_id, lifecycle_status, image_url, **product_content JSONB**, is_published） |
| `l6` | `base_configs` | 关联基准配置（JOIN 提供 form/bays/series） |
| `l6` | `server_types` | 类型 |

## 关键约定

- **新增入口统一为「尾卡 ＋」范式**：可增删区块（关联配置/亮点/维度/场景）一律在网格尾部放虚线「＋ 添加xx」卡（空态常驻），行式区块（技术规格/关键数字）用通栏虚线条；标题行不放「+ 添加」链接按钮（用户操作习惯定调）
- `product_content` 为 JSONB，后端按不透明 blob 透传：`server_catalog_repo._MODEL_FIELDS` 白名单含 `product_content`，写入 `json.dumps` + `CAST AS jsonb`，`_attach_base_config` 读出归一化为 dict（参见 `add_server_model_product_content.sql`）——**前端改 schema 零后端改动**
- `ModelProductContent` 类型见 `api/serverConfig.ts`：`{ tagline?, overview?, highlights?, capabilities?（含 icon 键 + metrics）, specs?, scenarios?（对象 name/fit/image）, docs?, features?（旧结构只读兼容） }`；`docs` 项为 `{name, url, size}`，url 为站内直链 `/api/server-catalog/model-docs/{原名净化}_{短uuid}.pdf`
- 机型资料 PDF 落 `backend/storage/model-docs/[{model_id}/]{原名净化}_{短uuid}.pdf`：机型独占文件照 drawing-svgs 先例**按机型子目录归档**（编辑已有机型时传 `?model_id=` 分类落盘，便于排查/清理）；新建机型尚未保存（无 id）落根目录，URL 落定后不再迁移。非内容寻址：同名重传产生新文件。**无独立删除端点**——引用计数保护下编辑中删除必被拒，故与图片池一样走保存时 diff GC（`PUT/DELETE /models/{id}` 算新旧 docs 差集，`count_doc_references` 全库兜底后删文件）；上传后未保存即离开会留孤儿文件（与图片池同语义，可接受）
- 能力图标键限定 `constants/capIcons.ts` 的 `CAP_ICON_KEYS`（chip/slots/net/drive/term/fan/shield/rack/mesh），详情页与编辑器共用同一注册表；管理页无 `--sun-color`，指示灯自动回落酒红 #FF7A4D
- 机型图片**内容寻址图片池**：上传（`type`=product 主图 / scenario 场景配图）落 `backend/storage/model-images/{原名}_{内容sha256前16位}.{ext}` 平铺池——同一张图重传/换机型/换用途都落到同一文件（幂等去重，URL 跨机型通用）；历史 `{机型名}/{type}/` 子目录存量继续可读。**换图即替换**：保存机型时主图/场景图旧 URL 若不再被任何机型或 banner 配置引用，文件自动删除；GET `/model-image/{path}` 兼容嵌套与平铺路径
- `a-auto-complete` 必须 `v-model:value` + options 只吃 `{value,label}[]`（项目已知坑）
- 骨架参照 `BaseConfigEditorPage`（顶栏 + `/new`&`:id` 路由复用），但**单栏流式**（非左右分栏）
