---
name: cpq-db-direct-query
description: "直连 CPQ PostgreSQL 的正确方法——别用 backend/.env 的 stale DATABASE_URL,用 config.py 默认 postgres/961216 + -X utf8 + connect_args"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 0aa265ad-5de4-4f99-a706-563646f639bb
  modified: 2026-10-23T07:22:47.324Z
---

直连 CPQ 数据库写脚本时,**别读 `backend/.env` 的 `DATABASE_URL`**——那是 stale 的(密码不对),连不上 → libpq 返回中文错误 → psycopg2 按 utf-8 解码炸 `UnicodeDecodeError ... 0xd6`。后端实际不读这条,见 `backend/app/core/config.py`。

**正确连法(2026-09-14 起仓库零硬编码, 密码只从 `backend/.env` 的 `POSTGRES_PASSWORD` 读):**
```python
env = dict(l.split("=",1) for l in Path("backend/.env").read_text(encoding="utf-8").splitlines() if "=" in l)
url = f"postgresql://postgres:{env['POSTGRES_PASSWORD'].strip()}@localhost:5432/cpq_platform?client_encoding=UTF8"
eng = create_engine(url, connect_args={"client_encoding":"UTF8"})
```
- 必须 `python -X utf8 script.py` 跑(否则中文报错解码炸;见 [[app-startup]] 的 -X utf8)。
- 用 SQLAlchemy + psycopg2(hermes venv `python` 有;`py` 没有)。
- 业务表都在**多 schema** 里(不是 public): `opportunities.opportunities` 主表 / `opportunities.quotations` / `opportunities.opportunity_requirements`; `ai_read.*` 是只读视图; `public` 几乎是空的——查 `information_schema.tables` 要带 schema 条件。

**Schema 结构(单库多 schema,见 `backend/app/models/base.py`):**
- `kp` — KP 配件库:`kp_parts`(id/category_id/oem_sku/brand/name/datasheet_url...)、`kp_part_specs`(id/part_id/spec_key/spec_value/sort_order)、`kp_categories`(id/name)。**配件库「分类」就是 kp_categories**,如 id=18「GPU card」。
- `l6`(料号库 parts_master 等)、`parts`(统一物料主表,新)、`opportunities`、`rules`、`l6_history`、`public`。

**Windows /tmp 路径坑:**
- Git Bash 的 `/tmp/x.json`(= MSYS 临时目录)和原生 Windows python 看到的 `/tmp/x.json`(=`当前盘:\tmp\...`)**不是一处**。
- 后果:curl 写 `/tmp/x.json` 没问题(bash 侧);但 `python -c "...open('/tmp/x.json')..."` 里 `/tmp` 是字符串、不被 MSYS 重写 → python 找不到文件。
- 解法:python 走 stdin(`cat /tmp/x.json | python -X utf8 -c "import json,sys;d=json.load(sys.stdin)"`),或把脚本路径**当参数**传(`python x.py` 的 arg 会被 MSYS 重写,文件内 open() 仍要用 Windows 路径)。

**Why:** 2026-07-31 为 Firecrawl 补 spec(见 [[firecrawl-spec-extract-poc]])直连库,连错 DATABASE_URL + 路径坑,连踩 4 次才通。
