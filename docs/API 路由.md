# API 路由

> 版本：v0.1.11 | 更新日期：2026-07-11

后端共 8 个路由模块（全部注册在 `backend/app/main.py`），前缀统一为 `/api/`。
此外根路由还提供 `GET /` 与 `GET /health` 两个系统端点。

> ⚠️ 重要变更：原"项目管理 `/api/projects`"模块已整体重命名为"商机管理 `/api/opportunities`"，路径参数由 `project_id` 改为 `opportunity_id`。原 `/api/quote/upload-to-project` 同步更名为 `/api/quote/upload-to-opportunity`。本文档基于重命名后的实际代码编写。

---

## 0 通用约定

### 鉴权

**当前无鉴权。** 全局未引入任何认证/授权机制：

- `main.py` 仅注册了 CORS 中间件，未添加任何鉴权依赖；
- 全部路由均未使用 `Depends(get_current_user)` / `HTTPBearer` / `OAuth` / API Key 等任何安全依赖；
- `admin/business-fields` 相关端点虽有 `operator` 查询参数（默认 `"system"`），但仅作为审计记录字段写入，**不做身份校验**；
- `pricing_engine.py` 第 1879 行留有 `# TODO: get from auth context` 注释，说明鉴权尚未实现。

> 这意味着所有端点（含价格管理、规则配置、永久删除等写操作）均对外完全开放。生产部署需自行在前端网关或反向代理层补充鉴权。

### Schema 组织方式

项目**没有独立的 schemas 包**（`backend/app/schemas/__init__.py` 为空文件）。所有 Pydantic 模型均**内联定义在各路由文件中**，且数量很少，仅以下 8 个：

| Schema 类 | 定义位置 | 用途 |
|-----------|---------|------|
| `CreateOpportunityRequest` | `api/opportunities.py` | 创建商机 |
| `UpdateOpportunityRequest` | `api/opportunities.py` | 更新商机基本信息 |
| `BatchOpportunityRequest` | `api/opportunities.py` | 批量操作商机 |
| `QuotationCreate` | `api/quotations.py` | 创建报价单 |
| `QuotationUpdate` | `api/quotations.py` | 更新报价单 |
| `BatchQuotationRequest` | `api/quotations.py` | 批量操作报价单 |
| `TemplateCreateRequest` / `TemplateUpdateRequest` | `api/export_templates.py` | 导出模板增改 |
| `CommentCreate` / `CommentResponse` | `api/comments.py` | 批注增查 |

**绝大多数写操作端点直接接收裸 `dict` 或 `list[dict]` 作为请求体**，无 Pydantic 校验；返回值也多为手工拼装的字典而非 ORM 序列化模型。下文凡标注"裸 dict"者即指此类无 schema 校验的接口。

### 通用错误响应

项目注册了三类全局异常处理器（`backend/app/core/exception_handlers.py`）：

| HTTP 状态码 | 触发条件 | 响应体 |
|------------|---------|--------|
| 400 | `RequestValidationError`（Pydantic 校验失败） | `{"detail": [...], "body": ...}` |
| 400 | `BusinessError`（业务异常） | `{"detail": "错误信息"}` |
| 500 | 未捕获异常 | `{"detail": "内部服务器错误"}` |

此外各端点内部常用 `raise HTTPException(status_code=4xx, detail="...")` 抛出业务错误，下文逐一标注。

### 通用数据模型

下列 ORM 模型的 `to_dict()` 输出在多个端点的响应中复用，统一在此说明：

**Opportunity（商机）** —— `models/opportunity.py`：
```
opportunity_id: str        folder_name: str        opportunity_name: str
customer_name: str         sales_person: str       fae: str
platform_type: str         chassis_form: str       total_qty: int
created_at: str            updated_at: str         status: str   # active/deleted
```

**Quotation（报价单）** —— `models/quotation.py`：
```
quotation_id: str          opportunity_id: str     version: str            quotation_name: str
file_path: str             l6_price: float         total_qty: int          config_count: int
created_at: str            updated_at: str         status: str             quotation_date: str
config_quantities: dict    config_descriptions: dict    config_server_models: dict
total_price: float         profit_margin: float
```

**OpportunityItem（报价单配置项）** —— `models/opportunity_item.py`：
```
item_id: int               quotation_id: str       config_name: str
category: str              part_name: str          spec: str
qty: int                   confirmed_price: float  base_price: float
final_price: float         profit_margin: float
```

---

## 1 报价模块 `/api/quote`

负责 Excel 报价单的上传解析、KP 历史价查询、L6 候选匹配。来源：`backend/app/api/quote.py`。

### POST `/api/quote/upload`
上传并解析 Excel 报价单（不落库，仅返回结构化预览数据，文件存入临时目录）。

- **请求**：`multipart/form-data`
  - `file`: UploadFile（必填，仅 `.xlsx` / `.xls`，≤50MB）
  - `opportunity_id`: str（可选 Form，不传则自动生成 `OPP_xxxxxxxxxxxx`）
- **响应 200**：
  ```jsonc
  {
    "status": "success",
    "message": "Quotation parsed and enriched successfully",
    "configs": { /* 见下方 process_upload 通用响应结构 */ },
    "opportunity_id": "OPP_xxxxxxxxxxxx",
    "temp_file": { "temp_path": "...", "original_name": "xxx.xlsx", "file_size": 12345 }
  }
  ```
- **错误**：400 文件非 Excel；413 文件超 50MB；500 解析失败。

### POST `/api/quote/upload-to-opportunity`
上传 Excel 到指定商机，解析后**立即创建报价单记录并持久化解析出的配置项**。

- **请求**：`multipart/form-data`
  - `file`: UploadFile（必填，`.xlsx`/`.xls`）
  - `opportunity_id`: str（**必填** Form）
- **响应 200**：同 `/upload`，额外含 `quotation_id: str`。
- **错误**：400 非 Excel；404 商机不存在；500 解析失败。

### POST `/api/quote/parse-preview`
仅解析预览（**不创建报价单**），供上传确认抽屉使用。

- **请求**：`multipart/form-data`，`file`: UploadFile（必填）
- **响应 200**：`process_upload` 结构 + `temp_file`（见下）。
- **错误**：400 非 Excel；500 解析失败。

### POST `/api/quote/confirm-upload`
用户在抽屉中确认 L6/KP 匹配后调用：解析 Excel、创建报价单记录、保存配置项。

- **请求**：`multipart/form-data`
  - `file`: UploadFile（必填）
  - `opportunity_id`: str（**必填** Form）
- **响应 200**：`process_upload` 结构 + `quotation_id` + `temp_file`。
- **错误**：400 非 Excel；404 商机不存在；500 解析失败。

> **`process_upload` 通用响应结构**（上述 4 个端点的 `configs` 字段）：
> ```jsonc
> {
>   "status": "success",
>   "message": "...",
>   "configs": {
>     "<config_name>": {
>       "items": [ { "category": "...", "part_name": "...", "spec": "...",
>                     "qty": 1, "base_price": 0.0, "profit_margin": 10.0,
>                     "final_price": 0.0, "match_status": "...", "is_usd_cpu": false } ],
>       "summary": { "l6_total": 0.0, "kp_total": 0.0, "warranty_total": 0.0, "grand_total": 0.0 },
>       "l6_matched_record": { /* L6 整机记录或 null */ },
>       "l6_meta": { /* Excel 解析出的原始需求 */ },
>       "warranty_info": { "l6": {...}, "kp": {...} }
>     }
>   }
> }
> ```

### GET `/api/quote/kp/history`
查询某型号 KP 的历史价格。

- **查询参数**：`model`: str（必填）
- **响应 200**：数组（裸 list），元素为历史价格记录（由 `PricingEngine.get_kp_price_history` 返回）。

### GET `/api/quote/l6/candidates`
按维度匹配，返回得分最高的前 3 个 L6 候选整机记录。

- **查询参数**（均可选）：`chassis`、`model`、`drive_bays`、`psu`、`motherboard`，均为 str
- **响应 200**：
  ```jsonc
  { "candidates": [ { /* L6 记录 */ , "match_score": 80, "matched_dims": 4, "total_dims": 5 } ] }
  ```

---

## 2 商机管理 `/api/opportunities`

> 原"项目管理 `/api/projects`"模块，已重命名。来源：`backend/app/api/opportunities.py`。

### POST `/api/opportunities/`
创建空商机（自动生成 `PRJ-YYYYMMDDHHMMSSffffff` 形式 ID，并创建物理文件夹）。

- **请求体**：`CreateOpportunityRequest`
  ```
  opportunity_name: str          # 必填
  customer_name: str = ""        # 选填
  notes: str = ""                # 选填（当前实现未使用 notes）
  ```
- **响应 200**：
  ```jsonc
  { "status": "success", "opportunity_id": "PRJ-...", "folder_name": "...", "message": "商机创建成功" }
  ```

### GET `/api/opportunities/list`
商机列表（分页）。

- **查询参数**：`page`: int=1、`page_size`: int=50、`include_deleted`: bool=false
- **响应 200**：
  ```jsonc
  { "items": [ {/* Opportunity.to_dict() + quotation_count + max_config_count */ } ], "total": 100 }
  ```
  > `items` 每项在商机字段基础上额外聚合 `quotation_count`、`max_config_count`（批量查询避免 N+1）。

### GET `/api/opportunities/{opportunity_id}`
商机详情（含报价单与配置）。

- **路径参数**：`opportunity_id`: str
- **响应 200**：`{ "status": "success", /* Opportunity 详情 + configs + quotations */ }`，由 `QuoteService.get_opportunity_details` → `PricingEngine.get_opportunity_details` 返回。
- **错误**：404 商机不存在。

### PUT `/api/opportunities/{opportunity_id}`
更新商机基本信息（仅更新非空字段）。

- **请求体**：`UpdateOpportunityRequest`（所有字段可选）
  ```
  opportunity_name?: str    customer_name?: str    total_qty?: int
  platform_type?: str       chassis_form?: str     sales_person?: str    fae?: str
  ```
- **响应 200**：`{ "status": "success", "message": "Project updated" }`
- **错误**：404 商机不存在。

### POST `/api/opportunities/save`
保存商机（含配置项移入商机文件夹，并同步 KP 价格到库）。

- **请求体**（裸 dict）：
  ```jsonc
  {
    "opportunity_info": { "opportunity_id": "...", "opportunity_name": "...", /* ... */ },
    "configs": { "<cfg>": { "items": [...], "description": "...", "server_model": "..." } },
    "config_quantities": { "<cfg>": 10 },
    "temp_file": { "temp_path": "...", "original_name": "..." }  // 可选
  }
  ```
- **响应 200**：`{ "status": "success", "opportunity_id": "...", "folder_name": "...", "kp_synced"?: int }`
- **错误**：500 内部错误（含数据处理/数据库错误明细）。

### POST `/api/opportunities/{opportunity_id}/export`
导出商机的 Excel，保存到 exports 文件夹并返回文件流下载。

- **查询参数**：`template_id`: str（可选）
- **响应 200**：`StreamingResponse`（`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，`Content-Disposition: attachment`）。
- **错误**：404 商机不存在。

### POST `/api/opportunities/{opportunity_id}/preview`
预览导出（生成 Excel 但不落盘，以附件形式返回）。

- **查询参数**：`template_id`: str（可选）
- **响应 200**：`StreamingResponse`（`Content-Disposition: inline`）。
- **错误**：404 商机不存在。

### POST `/api/opportunities/{opportunity_id}/preview-json`
预览导出为 JSON（`SheetRenderData[]` 结构，供前端 ExcelTable 组件渲染）。

- **查询参数**：`template_id`: str（可选）
- **响应 200**：
  ```jsonc
  { "sheets": [ { "name": "...", "cells": [[ { "row":1, "col":1, "value":..., "style": {...}, "merge"?:{...}, "rowSpan"?:2, "colSpan"?:2 } ]],
                  "rowCount": 10, "colCount": 8, "merges": [...], "rowHeights": {...}, "colWidths": {...} } ] }
  ```
- **错误**：404 商机不存在。

### POST `/api/opportunities/{opportunity_id}/trash`
移入回收站（软删除）。

- **响应 200**：`{ "status": "success" }`
- **错误**：500 内部错误。

### POST `/api/opportunities/batch-trash`
批量移入回收站。

- **请求体**：`BatchOpportunityRequest`：`opportunity_ids: List[str]`
- **响应 200**：`{ "success": ["PRJ-..."], "failed": [ { "id": "...", "error": "..." } ] }`

> 注：商机模块当前**仅实现了 `batch-trash`**，未实现 `batch-restore` / `batch-permanent-delete`（原文档列出的这两个端点在代码中不存在）。

### POST `/api/opportunities/{opportunity_id}/restore`
恢复商机。

- **响应 200**：`{ "status": "success" }`

### DELETE `/api/opportunities/{opportunity_id}`
永久删除商机。

- **响应 200**：`{ "status": "success" }`

### PUT `/api/opportunities/{opportunity_id}/meta`
更新商机元信息（任意键值，透传给 `repo.update_meta`）。

- **请求体**（裸 dict）：待更新字段，如 `{ "sales_person": "张三" }`
- **响应 200**：`{ "status": "success" }`

### 商机文件管理

以下端点均需先按 `opportunity_id` 查出 `folder_name`，再在其 `uploads/`、`exports/` 子目录操作；均做了路径穿越（path traversal）防护。

| 方法 | 路径 | 说明 | 请求参数 | 响应 |
|------|------|------|---------|------|
| GET | `/{opportunity_id}/files` | 实时扫描文件夹 | — | `{ "files": [ {name,size,modified,type("upload"/"export")} ], "total": n }` |
| GET | `/{opportunity_id}/files/download` | 下载文件 | 查询 `filename`: str（必填） | `FileResponse`；404 文件/商机不存在；403 非法路径 |
| POST | `/{opportunity_id}/files/upload` | 上传文件到 uploads | `multipart` `file`: UploadFile（白名单扩展名，≤50MB） | `{ "status":"success", "filename":..., "size":n }`；400 类型不符；413 超限 |
| PUT | `/{opportunity_id}/files/rename` | 重命名 | 查询 `old_name`、`new_name`（均必填 str） | `{ "status":"success", "old_name":..., "new_name":... }`；400 重名；404 未找到 |
| DELETE | `/{opportunity_id}/files` | 删除文件 | 查询 `filename`: str（必填） | `{ "status":"success", "filename":... }` |
| POST | `/{opportunity_id}/files/open` | 系统默认应用打开（仅本地部署） | 查询 `filename`: str | `{ "status":"success", "filename":... }`；403 可执行文件被拦截 |
| GET | `/{opportunity_id}/folder-path` | 获取文件夹绝对路径 | — | `{ "folder_path":..., "uploads_path":..., "exports_path":... }` |

> 允许上传扩展名白名单：`.xlsx .xls .csv .pdf .docx .doc .png .jpg .jpeg .gif .bmp .txt .zip`；`files/open` 拦截可执行扩展名 `.exe .bat .cmd .ps1 .vbs .sh .com .scr .msi .jar .py .rb .php .js`。

---

## 3 基准价格管理 `/api/admin`

来源：`backend/app/api/admin.py`。分三大块：KP 零件、L6 整机、业务字段管理。

### 3.1 元数据

#### GET `/api/admin/metadata-fields`
返回可用元数据字段列表。
- **响应 200**：`{ "fields": ["opportunity_name","model_name","customer_name","sales_person","fae","date","total_qty","platform_type","chassis_form","company","l6_spec","description","model_qty"] }`

### 3.2 KP（零件）

#### GET `/api/admin/kp/categories`
- **响应 200**：`{ "categories": [...] }`

#### GET `/api/admin/kp/by-category`
- **查询参数**：`category`: str（必填）、`search`: str=""
- **响应 200**：`{ "items": [...], "total": n }`

#### GET `/api/admin/kp/list`
KP 最新价格列表（分页+搜索+排序）。
- **查询参数**：`page`:int=1、`page_size`:int=20、`search`:str=""、`category`:str=""、`sort_by`:str="date"、`sort_order`:str="desc"
- **响应 200**：`{ "items": [...], "total": n }`

#### POST `/api/admin/kp/update`
更新 KP 价格（插入新记录，保留历史）。
- **请求体**（裸 dict）：`model`/`part_name`（二选一）、`price`（必填）、`spec`=""、`category`="Key Parts"、`currency`="RMB"、`note`="手动更新"
- **响应 200**：`{ "status":"success", "message":"Price updated" }`
- **错误**：400 缺 model 或 price。

#### POST `/api/admin/kp/rename`
- **请求体**（裸 dict）：`old_model`: str、`new_model`: str（均必填）
- **响应 200**：`{ "status": "success" }`；400 缺参数。

#### POST `/api/admin/kp/update-note`
- **请求体**（裸 dict）：`model`: str（必填）、`note`: str=""
- **响应 200**：`{ "status": "success" }`；400 缺 model。

#### GET `/api/admin/kp/history`
- **查询参数**：`model` 或 `part_name`（至少一个）
- **响应 200**：历史记录数组（裸 list）；400 二者皆缺。

### 3.3 L6（整机）

#### GET `/api/admin/l6/list`
- **查询参数**：`page`:int=1、`page_size`:int=20、`search`:str=""
- **响应 200**：`{ "items": [...], "total": n }`（异常时返回 `{ "items":[], "total":0, "error":"..." }`）

#### GET `/api/admin/l6/grouped`
按机型聚合分组。
- **查询参数**：`search`: str=""
- **响应 200**：`{ "groups": [...], "total": n }`

#### POST `/api/admin/l6/create`
新增 L6 记录（并写入历史快照）。
- **请求体**（裸 dict），必填：`chassis`、`model`、`price`；可选：`motherboard`、`backplane`、`gpu_expansion`、`psu`、`drive_bays`、`rail_kit`、`power_cord`、`update_date`、`note`
- **响应 200**：`{ "status":"success", "message":"L6 record created", "id": <new_id> }`；400 缺必填字段。

#### POST `/api/admin/l6/update`
更新 L6 记录（更新价格时同步写历史快照）。
- **请求体**（裸 dict）：`id`/`rowid`（必填）+ 任意待更新字段；含 `price` 时触发历史快照
- **响应 200**：`{ "status":"success", "message":"L6 record updated" }`；400 缺 ID。

#### DELETE `/api/admin/l6/{record_id}`
- **路径参数**：`record_id`: int
- **响应 200**：`{ "status":"success", "message":"L6 record deleted" }`

#### GET `/api/admin/l6/{record_id}/history`
- **路径参数**：`record_id`: int；**查询**：`limit`:int=50
- **响应 200**：`{ "history": [...], "total": n }`

#### PUT `/api/admin/l6/sort-order`
批量更新排序。
- **请求体**（裸 dict）：`{ "items": [ {id, sort_order}, ... ] }`
- **响应 200**：`{ "status":"success", "message":"Sort order updated" }`；400 缺 items。

### 3.4 业务字段管理 `/api/admin/business-fields`

> 这是原文档**完全缺失**的一整块功能（共 19 个端点），用于动态业务字段的增删改查、引用管理、校验、使用统计、导入导出。请求体绝大多数为裸 dict。

#### 字段定义 CRUD
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/business-fields` | — | 字段列表（含禁用） |
| POST | `/business-fields` | 裸 dict：`key`/`label`/`category`/`source`（必填）；查询 `operator`:str="system" | 新建字段对象；409 key 已存在 |
| PUT | `/business-fields/{field_key}` | 裸 dict（待更新字段）；查询 `operator` | 更新后字段；404 未找到 |
| DELETE | `/business-fields/{field_key}` | 查询 `operator` | `{ "success": true }` 或 `{ "success": false, "has_references": true, "references": [...], "message":... }`（存在引用时拦截） |
| DELETE | `/business-fields/{field_key}/force` | 查询 `operator` | `{ "success": true, "message":"字段已强制删除" }`（忽略引用） |
| PUT | `/business-fields/sort-order` | 裸 dict：`{ "items": [...] }` | `{ "status":"success", "message":"Sort order updated" }` |

#### 字段引用管理
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/business-fields/{field_key}/references` | — | `{ "field_key":..., "references": [...], "total": n }` |
| POST | `/business-fields/{field_key}/references` | 裸 dict：`ref_type`/`ref_id`（必填）、`ref_name?` | 新引用对象；404 字段不存在 |
| DELETE | `/business-fields/{field_key}/references/{ref_type}/{ref_id}` | 路径 `ref_type`:str、`ref_id`:int | `{ "success": true }`；404 未找到 |
| POST | `/business-fields/check-references` | 裸 dict：`{ "keys": [...] }` | `{ "references": {...}, "total_fields_with_refs": n }` |

#### 字段校验
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| POST | `/business-fields/{field_key}/validate` | 裸 dict：`{ "value": ... }` | 校验结果对象 |
| POST | `/business-fields/validate-batch` | 裸 dict：`{ "values": { "<field_key>": <value> } }` | `{ "valid": bool, "results": { "<key>": {...} } }` |

#### 变更历史
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/business-fields/{field_key}/history` | 查询 `limit`:int=50 | `{ "field_key":..., "history": [...], "total": n }`；404 字段不存在 |

#### 使用统计
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/business-fields/{field_key}/stats` | — | 统计对象；404 未找到 |
| GET | `/business-fields-usage-stats` | — | `{ "stats": [...], "total": n }` |
| POST | `/business-fields/{field_key}/record-usage` | — | `{ "success": true }` |
| POST | `/business-fields/record-usage-batch` | 裸 dict：`{ "keys": [...] }` | `{ "success": true, "count": n }` |

#### 导入导出
| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/business-fields-export` | 查询 `keys`:str（逗号分隔，可选） | `{ "fields": [...], "total": n, "exported_at": "ISO时间" }` |
| POST | `/business-fields-import` | 裸 dict：`{ "fields": [...] }`（必填）、`mode`:"skip"/"overwrite"（默认 skip）；查询 `operator` | 导入结果对象；400 缺 fields 或 mode 非法 |

---

## 4 规则管理 `/api/rules`

来源：`backend/app/api/rules.py`。本模块**几乎所有端点请求体均为裸 dict / list[dict]**，无 Pydantic 校验。

### 4.1 辅助查询

#### GET `/api/rules/cpu-list`
从 KP 库获取去重 CPU 型号列表。
- **响应 200**：`{ "cpus": [...] }`

#### GET `/api/rules/l6/list`
获取 L6 全量记录（匹配规则演示用）。
- **响应 200**：`{ "records": [...], "total": n }`

#### POST `/api/rules/l6/preview-match`
逐步预览 L6 匹配过程。
- **请求体**（裸 dict）：`{ chassis, model, drive_bays, psu, motherboard }`
- **响应 200**：匹配过程结果（由 `PricingEngine.preview_l6_match` 返回）。

### 4.2 区域配置

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/l6-region-config` | — | `{ "config": [...] }` |
| POST | `/l6-region-config` | 裸 dict（`region_start_keywords`/`field_mapping`/`region_end_keywords`） | `{ "id": <id>, "status": "success" }` |
| PUT | `/l6-region-config/{config_id}` | 路径 `config_id`:int + 裸 dict | `{ "status": "success" }`；404 未找到 |
| GET | `/kp-region-config` | — | `{ "config": [...] }` |
| POST | `/kp-region-config` | 裸 dict | `{ "id": <id>, "status": "success" }` |
| PUT | `/kp-region-config/{config_id}` | 路径 `config_id`:int + 裸 dict | `{ "status": "success" }`；404 未找到 |

### 4.3 KP 分类映射

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/kp-category-mappings` | — | `{ "mappings": [...] }` |
| PUT | `/kp-category-mappings` | `list[dict]`（批量） | 仓库返回值 |
| PUT | `/kp-category-mappings/{mapping_id}` | 路径 int + 裸 dict | `{ "status": "success" }`；404 |
| POST | `/kp-category-mappings` | 裸 dict（`keyword`/`category`/`priority`） | `{ "id": <id>, "status": "success" }` |
| DELETE | `/kp-category-mappings/{mapping_id}` | 路径 int | `{ "status": "success" }`；404 |

### 4.4 主板映射

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/motherboard-mappings` | — | `{ "mappings": [...] }` |
| PUT | `/motherboard-mappings` | `list[dict]`（批量） | 仓库返回值 |
| PUT | `/motherboard-mappings/{mapping_id}` | 路径 int + 裸 dict | `{ "status": "success" }`；404 |
| POST | `/motherboard-mappings` | 裸 dict（`cpu_feature`/`motherboard_model`/`priority`） | `{ "id": <id>, "status": "success" }` |
| DELETE | `/motherboard-mappings/{mapping_id}` | 路径 int | `{ "status": "success" }`；404 |

### 4.5 L6 匹配规则

| 方法 | 路径 | 请求 | 响应 |
|------|------|------|------|
| GET | `/matching-rules` | — | `{ "rules": [...] }` |
| PUT | `/matching-rules` | `list[dict]`（批量） | 仓库返回值 |
| GET | `/matching-rules/{rule_name}` | 路径 str | 单条规则对象；404 |
| PUT | `/matching-rules/{rule_name}` | 裸 dict：`{ "rule_value": ... }`（必填） | `{ "status": "success" }`；400 缺 rule_value；404 |
| POST | `/matching-rules` | 裸 dict（`rule_name`/`rule_value`/`description`） | `{ "id": <id>, "status": "success" }` |
| DELETE | `/matching-rules/{rule_id}` | 路径 int | `{ "status": "success" }`；404 |

### 4.6 解析预览

#### POST `/api/rules/parse-preview`
上传 Excel 进行热力图预览，返回网格 + 单元格标记 + 元信息。
- **请求**：`multipart/form-data`
  - `file`: UploadFile（必填）
  - `template_config`: str（Form，默认 `"{}"`，JSON 字符串，含 `kp_mappings`）
- **响应 200**：`PricingEngine.preview_parse` 结果（含 `sheet_name`、网格、单元格标记等）。
- **错误**：400 无法解析/无有效 Sheet/Sheet 为空。

### 4.7 数字精度（原文档缺失）

#### GET `/api/rules/number-precision`
- **响应 200**：`{ "precision": <int> }`（允许值 0/2/4）

#### PUT `/api/rules/number-precision`
- **请求体**（裸 dict）：`{ "precision": int }`（必须为 0/2/4）
- **响应 200**：`{ "status": "success", "precision": <int> }`；400 非法值。

### 4.8 导出分类

#### GET `/api/rules/export-categories`
- **响应 200**：`{ "custom": [...] }`

#### PUT `/api/rules/export-categories`
- **请求体**（裸 dict）：`{ "custom": [...] }`
- **响应 200**：`{ "status": "success" }`；500 更新失败。

### 4.9 初始化默认规则

#### POST `/api/rules/init-defaults`
若规则库为空则写入默认 L6/KP 区域配置、KP 分类映射、主板映射、匹配规则。
- **响应 200**：`{ "status": "success", "message": "Default rules initialized" }` 或 `{ "status": "already_initialized", "message": "Rules already exist" }`。

---

## 5 导出模板 `/api/export-templates`

来源：`backend/app/api/export_templates.py`。

#### GET `/api/export-templates/fields`
获取所有**启用**业务字段（供模板绑定，来自数据库）。
- **响应 200**：业务字段数组。

#### GET `/api/export-templates/fields/all`
获取全部业务字段（**含禁用**，供管理用）。
- **响应 200**：业务字段数组。

#### GET `/api/export-templates`
模板列表。
- **响应 200**：模板数组。

#### GET `/api/export-templates/{template_id}`
- **路径参数**：`template_id`: int
- **响应 200**：模板对象；404 未找到。

#### POST `/api/export-templates`
- **请求体**：`TemplateCreateRequest`
  ```
  display_name: str          # 必填
  template_json: dict = {}   # 选填
  ```
- **响应 200**：新建模板对象（`name` 自动生成为 `时间戳_4位随机`）。500 生成唯一标识失败。

#### PUT `/api/export-templates/{template_id}`
- **请求体**：`TemplateUpdateRequest`（均可选）
  ```
  display_name?: str
  template_json?: dict
  ```
- **响应 200**：更新后模板对象；404 未找到。

#### DELETE `/api/export-templates/{template_id}`
- **响应 200**：`{ "success": true }`；404 未找到。

#### POST `/api/export-templates/{template_id}/set-default`
- **响应 200**：`{ "success": true }`；404 未找到。

---

## 6 批注 `/api/comments`

来源：`backend/app/api/comments.py`。路径参数为 `opportunity_id`（原 `project_id` 已更名）。

#### POST `/api/comments/`
- **请求体**：`CommentCreate`
  ```
  opportunity_id: str        # 必填
  content: str               # 必填（不能为空）
  user_name: str = "匿名"    # 选填
  ```
- **响应 200**（`response_model=CommentResponse`）：`{ "id": int, "opportunity_id": str, "user_name": str, "content": str, "created_at": "刚刚" }`
- **错误**：400 内容为空。

#### GET `/api/comments/{opportunity_id}`
- **响应 200**（`response_model=List[CommentResponse]`）：批注数组，元素含 `id`、`opportunity_id`、`user_name`、`content`、`created_at`。

#### GET `/api/comments/{opportunity_id}/count`
- **响应 200**：`{ "count": int }`

#### DELETE `/api/comments/{comment_id}`
- **路径参数**：`comment_id`: int
- **响应 200**：`{ "message": "删除成功" }`；404 不存在。

---

## 7 看板 `/api/dashboard`

来源：`backend/app/api/dashboard.py`。

#### GET `/api/dashboard/stats`
首页统计。
- **响应 200**：
  ```jsonc
  {
    "total_opportunities": int,
    "total_configs": int,            // 报价单总数
    "new_opportunities_this_week": int,
    "new_configs_this_week": int
  }
  ```

#### GET `/api/dashboard/trend`
近 N 天每日商机/报价单创建趋势。
- **查询参数**：`days`: int=30
- **响应 200**：数组，元素 `{ "date": "YYYY-MM-DD", "opportunities": int, "configs": int }`（补齐零值日期）。

---

## 8 报价单 `/api/quotations`

来源：`backend/app/api/quotations.py`。

#### GET `/api/quotations`
报价单列表。
- **查询参数**：`opportunity_id`: str（可选）、`include_deleted`: bool=false
- **响应 200**：`{ "quotations": [ Quotation.to_dict() ] }`

#### GET `/api/quotations/{quotation_id}`
获取单个报价单（含配置项、商机信息、每配置 L6 数据）。
- **路径参数**：`quotation_id`: str
- **查询参数**：`reparse`: bool=false（为 true 时重新解析源 Excel 重建 per-config L6，性能开销大）
- **响应 200**：`Quotation.to_dict()` 基础上叠加：
  ```jsonc
  {
    /* ...Quotation 字段... */
    "opportunity_name": str, "customer_name": str, "date": str, "description": str,
    "items": [ OpportunityItem.to_dict() ],
    "per_cfg_l6": { "<cfg>": { "l6_meta": {...}, "l6_matched_record": {...}|null } },
    "l6_matched_record": {...}|null,   // 兼容旧调用方，取首个配置
    "l6_meta": {...}
  }
  ```
- **错误**：404 未找到。

#### POST `/api/quotations`
创建报价单。
- **请求体**：`QuotationCreate`
  ```
  opportunity_id: str               # 必填
  file_path?: str
  quotation_date?: str
  quotation_name?: str
  ```
- **响应 200**：`{ "quotation_id": str, "quotation": Quotation.to_dict() }`
- **错误**：404 商机不存在。

#### PUT `/api/quotations/{quotation_id}`
- **请求体**：`QuotationUpdate`（均可选）
  ```
  l6_price?: float        total_qty?: int       config_count?: int
  config_quantities?: dict    quotation_date?: str    quotation_name?: str
  ```
- **响应 200**：`{ "quotation": Quotation.to_dict() }`；404 未找到。

#### PATCH `/api/quotations/{quotation_id}/l6`
更新报价单的 L6 匹配记录（用户手动改选机型时调用）。**原文档缺失此端点。**
- **请求体**（裸 dict）：`l6_record`（新的 L6 记录对象）
- **响应 200**：`{ "success": true, "l6_record": {...} }`；404 未找到；500 更新失败。

#### DELETE `/api/quotations/{quotation_id}`
软删除报价单。
- **响应 200**：`{ "message": "Quotation deleted" }`；404 未找到。

#### POST `/api/quotations/{quotation_id}/restore`
恢复软删除的报价单。
- **响应 200**：`{ "message": "Quotation restored" }`；404 未找到。

#### GET `/api/quotations/{quotation_id}/items`
- **响应 200**：`{ "items": [ OpportunityItem.to_dict() ] }`

#### POST `/api/quotations/{quotation_id}/items`
保存配置项及各配置的数量/描述/服务器型号。
- **请求体**（裸 dict 或 list，兼容两种格式）：
  ```jsonc
  // 新格式（dict）
  { "items": [...], "config_quantities"?: {...}, "config_descriptions"?: {...}, "config_server_models"?: {...} }
  // 旧格式（list）：直接传 items 数组
  ```
- **响应 200**：`{ "saved": <count> }`

#### POST `/api/quotations/batch-delete`
- **请求体**：`BatchQuotationRequest`：`quotation_ids: List[str]`
- **响应 200**：`{ "success": [...], "failed": [ { "id":..., "error":... } ] }`

#### POST `/api/quotations/batch-restore`
- **请求体**：`BatchQuotationRequest`
- **响应 200**：`{ "success": [...], "failed": [...] }`

#### POST `/api/quotations/batch-permanent-delete`
批量永久删除报价单（连带删除其配置项）。
- **请求体**：`BatchQuotationRequest`
- **响应 200**：`{ "success": [...], "failed": [...] }`；500 整体失败时回滚。

---

## 附：系统端点（`main.py`）

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/` | 根欢迎页 | `{ "message": "Welcome to CPQ Platform API v{APP_VERSION}", "status": "running" }`（版本取自 config.py） |
| GET | `/health` | 健康检查 | `{ "status": "ok" }` |

> 注：根端点版本号取自 `config.py` 的 `APP_VERSION`（当前 `0.1.11`），不再硬编码。

---

## 附录：端点统计

| 模块 | 前缀 | 端点数 |
|------|------|--------|
| 报价 | `/api/quote` | 6 |
| 商机管理 | `/api/opportunities` | 20 |
| 基准价格管理 | `/api/admin` | 34（KP 8 + L6 7 + 业务字段 19） |
| 规则管理 | `/api/rules` | 31 |
| 导出模板 | `/api/export-templates` | 8 |
| 批注 | `/api/comments` | 4 |
| 看板 | `/api/dashboard` | 2 |
| 报价单 | `/api/quotations` | 12 |
| 系统端点 | `/` | 2 |
| **合计** | | **119** |

---

*最后基于代码核对日期：2026-07-11*
