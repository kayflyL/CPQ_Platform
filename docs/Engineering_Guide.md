# 工程实操指南（Engineering Guide）

> 版本：v0.1.11 | 适用对象：后端/前端开发者、运维部署人员
> 本文基于实际代码与配置编写，所有命令、路径、机制均可在源码中核实。

---

## 目录

1. [环境搭建与首次初始化](#1-环境搭建与首次初始化)
2. [配置项完整说明](#2-配置项完整说明)
3. [测试](#3-测试)
4. [生产部署](#4-生产部署)
5. [排错与常见坑](#5-排错与常见坑)

---

## 1. 环境搭建与首次初始化

### 1.1 前置依赖

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.11+ | 代码使用了 `dict \| None` 等 3.10+ 语法及 SQLAlchemy 2.0 / pydantic 2.x |
| Node.js | 18+ | Vite 8 驱动的前端构建 |
| 包管理器（Python） | pip 或 uv | 项目当前以 `requirements.txt` 管理依赖（**未提供 `pyproject.toml` / `uv.lock`**） |
| 包管理器（前端） | npm | 随 Node 附带 |

> **关于 uv**：仓库内没有 `pyproject.toml`，因此 `uv sync`（依赖 lock 文件的标准 uv 工作流）目前不适用。下文统一使用 `pip install -r requirements.txt`。如果你习惯 uv，等价命令为 `uv pip install -r requirements.txt`，运行测试用 `uv run pytest`。

### 1.2 后端安装

```bash
cd backend

# 方式一：标准虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 方式二：uv
uv venv
uv pip install -r requirements.txt
```

`requirements.txt` 关键依赖：`fastapi`、`uvicorn[standard]`、`sqlalchemy>=2.0`、`pydantic`、`pydantic-settings`、`pandas`、`openpyxl`、`python-multipart`、`pytest`。

### 1.3 `.env` 配置

在 `backend/` 下创建 `.env`（与 `app/core/config.py` 的 `Config.env_file = ".env"` 对应）。仓库未提供 `.env.example`，需手动创建。完整示例见 [§2.3](#23-完整-env-示例)。

最小可用 `.env`：

```ini
DATA_PATH=D:\Quotation_Automation
DEBUG=true
```

### 1.4 前端安装

```bash
cd frontend
npm install
```

前端无自定义环境变量（未使用 `import.meta.env` / `VITE_` 前缀变量）。开发期 API 请求走相对路径 `/api`，由 Vite dev server 代理转发到后端（见 `vite.config.ts` 的 `server.proxy`，target 为 `http://localhost:8000`）。

### 1.5 首次运行初始化机制（重要）

> **结论先行：首次启动只会自动创建 `rules.db` 与 `l6_history.db` 的表，并灌入默认业务规则；`kp_data.db`、`l6_data.db`、`opportunities.db` 的表不会自动创建，KP/L6 基础数据需手动灌入。**

#### 1.5.1 启动链路

`backend/app/main.py` 使用 FastAPI 的 `lifespan` 上下文管理器（非旧版 `@app.on_event`）注册启动事件：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_rules_db()   # ← 唯一的启动逻辑
    yield
```

`init_rules_db()` 定义在 `backend/app/core/startup.py`，它做了三件事：

1. **建表（仅两个库）**
   ```python
   Base.metadata.create_all(bind=rules_engine)       # rules.db
   Base.metadata.create_all(bind=l6_history_engine)  # l6_history.db
   ```
   注意：`Base` 是所有 ORM 模型共享的 `DeclarativeBase`。`create_all` 会把当时**已导入到 `Base.metadata` 的所有表**都建到传入的 engine 对应库中。因此 `rules.db` 与 `l6_history.db` 实际上会被塞入一批"冗余空表"（如 opportunities、quotations 等），但只有各自真正使用的表会被读写。

2. **灌入默认规则（仅当对应表为空时）**
   - L6 区域识别配置（`l6_region_config`）
   - KP 区域识别配置（`kp_region_config`）
   - KP 分类关键词映射（`kp_category_mapping`，18 条默认项：cpu/memory/hdd/gpu/…）
   - 主板映射（`motherboard_mapping`，7 条：KH50000→Polaris MB、AMD/INTEL→TTY TG658V3 等）
   - 匹配规则（`matching_rules`：5 维匹配维度、降级维度、价格差异阈值 0.01）

3. **清理临时文件**：调用 `FileStorage.cleanup_temp()`，删除 `storage/_temp/` 下超过 24 小时的上传临时文件。

#### 1.5.2 哪些库/表不会被自动创建

| 库 | 缺失的表 | 原因 |
|----|----------|------|
| `kp_data.db` | `kp_records` | 使用原生 SQL（`KPRepository` 直连 `kp_engine`），**无对应 ORM 模型**，`create_all` 建不出来 |
| `l6_data.db` | `l6_records` | 同上，`L6Repository` 用原生 SQL |
| `opportunities.db` | `opportunities`、`quotations`、`opportunity_items` 等 | 虽有 ORM 模型，但 startup **未对 `opp_engine` 调用 `create_all`** |

这意味着：首次启动后访问 KP/L6/商机相关接口会因"no such table"报错。**必须先手动建表或从已有环境复制数据库文件**（见 [§1.7](#17-首次灌入-kpl6-基础数据)）。

#### 1.5.3 手动初始化全部库（推荐做法）

启动应用前，先确保 `DATA_PATH\Reference\` 目录存在，再针对 KP/L6/Opportunities 库补建表。`kp_records` 与 `l6_records` 无 ORM 模型，需手写 DDL：

```sql
-- kp_data.db
CREATE TABLE IF NOT EXISTS kp_records (
    category TEXT, model TEXT, price REAL,
    currency TEXT, date TEXT, note TEXT
);

-- l6_data.db（字段以 l6_repo.py 实际查询为准）
CREATE TABLE IF NOT EXISTS l6_records (
    chassis TEXT, model TEXT, motherboard TEXT, backplane TEXT,
    gpu_expansion TEXT, psu TEXT, drive_bays TEXT, rail_kit TEXT,
    power_cord TEXT, price REAL, update_date TEXT, note TEXT,
    sort_order INTEGER DEFAULT 0
);
```

`opportunities.db` 的 ORM 表可一次性建出（在 `backend/` 下执行）：

```python
# 临时脚本：建 opportunities.db 全部 ORM 表
from app.models.base import opp_engine, Base
# 触发所有模型导入
import app.models.opportunity, app.models.quotation, app.models.opportunity_item
import app.models.opportunity_file
Base.metadata.create_all(bind=opp_engine)
print("opportunities.db 表已创建")
```

> 提示：`backend/scripts/init_business_fields.py` 中有对 `kp_engine` 调用 `create_all` 的逻辑，用于初始化业务字段管理表（`business_fields` 等存放在 `kp_data.db`，由 `BusinessFieldRepository` 经 `KP_SessionLocal` 访问）。

### 1.6 DATA_PATH 目录结构

`DATA_PATH`（默认 `D:\Quotation_Automation`）是所有数据库与配置的根目录。结构如下：

```
D:\Quotation_Automation\
├── Reference\                      ← 6 个 SQLite 库所在目录（base.py 中 DATA_DIR）
│   ├── kp_data.db                  ← KP 零件价格、业务字段
│   ├── l6_data.db                  ← L6 整机型号
│   ├── l6_history.db               ← L6 价格变更历史
│   ├── rules.db                    ← 业务规则、导出模板（自动建表+默认数据）
│   ├── opportunities.db            ← 商机/报价单/配置项
│   └── comments.db                 ← 商机批注（原生 sqlite3 管理，非 base.py）
├── config.json                     ← 报价系数（税率/汇率/利润率/质保费率，可选，缺失时用默认值）
└── (其余业务文件)
```

- `Reference\` 子目录是 6 个库的固定存放位置，由 `models/base.py` 的 `DATA_DIR = os.path.join(DATA_PATH, "Reference")` 决定。
- `config.json` 由 `QuoteService._load_config()` 与 `PricingEngine._load_config()` 读取，缺失时回退到默认值 `{"tax_rate": 0.13, "usd_to_rmb": 7.0, "profit_margin": 0.1, "warranty_fee_rate": 0.02}`。

> **注意**：`base.py` 只做 `os.path.join` 拼接路径，**不会自动创建 `Reference\` 目录**。首次运行前该目录必须已存在，否则 SQLite 连接会失败（SQLite 不会自动创建多级缺失目录）。参见 [§5.6](#56-data_path-目录不存在时的行为)。

另：文件存储（上传/导出的 Excel 等）使用独立目录 `backend/storage/`（由 `FileStorage` 管理，`__init__` 中 `mkdir(parents=True, exist_ok=True)` 会自动创建），不在 `DATA_PATH` 之下。

### 1.7 首次灌入 KP/L6 基础数据

KP 与 L6 的基础价格数据无法通过启动事件灌入，可选途径：

1. **从已有环境复制**（最快）：把旧环境的 `kp_data.db`、`l6_data.db` 直接拷贝到 `DATA_PATH\Reference\`。
2. **通过后台管理界面录入**：前端"KP 管理""L6 管理"页面提供增删改查，调用 `/api/admin/kp/update`、`/api/admin/l6/create` 等接口逐条录入。
3. **通过 Excel 报价自动沉淀**：用户在报价工作台上传含 KP 明细的 Excel 后，`PricingEngine.sync_kp_prices_to_db()` 会把新价格写入 `kp_records`（仅在价格变化时插入新记录）。

> `rules.db` 的默认规则无需手动操作——`init_rules_db()` 与 `/api/rules/init-defaults` 端点都会在表为空时自动灌入。两者逻辑一致（默认值硬编码在代码中）。

---

## 2. 配置项完整说明

配置类：`backend/app/core/config.py` → `Settings(BaseSettings)`，通过 `@lru_cache` 的 `get_settings()` 单例读取，支持 `.env` 文件与环境变量覆盖。

### 2.1 逐项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `APP_NAME` | str | `"CPQ Platform"` | 应用名，传给 `FastAPI(title=...)` |
| `APP_VERSION` | str | `"0.1.11"` | 应用版本，传给 `FastAPI(version=...)`；根路由 `/` 的欢迎消息也通过 `settings.APP_VERSION` 动态取值 |
| `DEBUG` | bool | `false`（读 `DEBUG` 环境变量，`"true"` 为真） | 调试开关。当前代码仅作声明保留，未在关键路径上分支使用 |
| `DATABASE_URL` | str | `"sqlite:///./data/cpq_platform.db"` | ⚠️ **遗留字段，当前未被有效使用**。全代码库无任何模块引用 `settings.DATABASE_URL`。实际数据存放在 6 个独立 SQLite 库（见 §1.6）。保留它仅为兼容旧配置，请勿以为改它会改变数据存储位置 |
| `DATA_PATH` | str | `r"D:\Quotation_Automation"` | 数据根目录。6 个库位于其下的 `Reference\` 子目录；`config.json` 位于其根。**生产环境务必显式设置** |
| `CORS_ORIGINS` | list[str] | `["http://localhost:5173", "http://127.0.0.1:5173"]` | 允许跨域的前端来源。生产环境需加入实际域名。`.env` 中以 JSON 数组字符串形式书写 |

> `Config` 内 `extra = "allow"`：允许 `.env` 中出现 `Settings` 未声明的字段而不报错。

### 2.2 CORS 中间件实际配置

`main.py` 中：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,      # 注意：凭据设为 False
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_credentials=False` 意味着不支持 Cookie 跨域携带——前端若未来引入 Cookie/Session 认证需改为 `True` 并收窄 `allow_origins`。

### 2.3 完整 `.env` 示例

```ini
# ===== 应用信息 =====
APP_NAME=CPQ Platform
APP_VERSION=0.1.11
DEBUG=true

# ===== 数据路径（6 个 SQLite 库的根目录，库实际在其 Reference\ 子目录下）=====
DATA_PATH=D:\Quotation_Automation

# ===== 遗留字段（当前未生效，保持默认即可，改动无效果）=====
DATABASE_URL=sqlite:///./data/cpq_platform.db

# ===== CORS（JSON 数组格式，生产环境改为实际前端域名）=====
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

> 生产环境示例见 [§4.4](#44-生产环境变量取值建议)。

---

## 3. 测试

### 3.1 后端测试文件

测试位于 `backend/tests/`，共两个测试模块 + 一个 fixture 配置：

| 文件 | 覆盖范围 |
|------|----------|
| `conftest.py` | Pytest 全局配置与公共 fixture（见 §3.2） |
| `test_pricing_engine.py` | `PricingEngine` 的初始化、`parse_file`（空字典/跳过 Reference Sheet/跳过空 Sheet）、`match_l6_total`（无记录/精确匹配/部分匹配）、`_extract_meta`、`_parse_items` |
| `test_quote_service.py` | `QuoteService` 的初始化（验证 5 个 repo 与 engine 被创建）、`_load_config`（文件存在/不存在两种情况）、`process_upload` 基本流程 |

> `backend/` 下还有若干游离脚本（如 `test_file_tracking.py`）和 `backend/scripts/` 下的 `test_*.py`，这些不属于正式 pytest 套件，多为一次性验证脚本。

### 3.2 conftest.py 的 fixture 机制

**核心特点：全部使用 `unittest.mock.MagicMock`，不连接任何真实数据库。**

- `mock_kp_repo` / `mock_l6_repo` / `mock_project_repo` / `mock_rules_repo` / `mock_export_template_repo`：均为 `MagicMock`，预设 `return_value=[]`，使 `PricingEngine` 在无数据状态下可被实例化与调用。
- `sample_l6_data` / `sample_kp_data` / `sample_excel_df`：提供内存中的样例字典 / pandas DataFrame，用于喂给被测方法。

也就是说：测试既不用临时库也不用内存库（`:memory:`），而是通过 mock 把 Repository 层完全架空，只验证引擎/服务的纯逻辑。这意味着 **数据库层（原生 SQL、表结构）没有自动化测试覆盖**。

> ⚠️ **测试套件当前疑似失败（命名脱节）**：`pricing_engine.py` 的 `__init__` 参数已改名 `opportunity_repo`（~L103-108），但 conftest 的 fixture 仍叫 `mock_project_repo`、测试断言仍写 `engine.project_repo`（访问不存在的属性）。位置传参能实例化引擎，但 `assert engine.project_repo == mock_project_repo` 会抛 `AttributeError`。跑 `python -m pytest` 前请预期失败；修复需把测试里的 `project_repo` 统一改为 `opportunity_repo`。

### 3.3 运行命令

```bash
cd backend

# 标准方式
python -m pytest                    # 跑全部
python -m pytest -v                 # 详细输出
python -m pytest tests/test_pricing_engine.py   # 单个文件

# 若使用 uv
uv run pytest
```

测试不会改动任何真实数据文件，可在任意环境安全运行。

### 3.4 前端测试

**前端目前没有测试。** `frontend/package.json` 的 `scripts` 仅含 `dev` / `build` / `preview`，无 `test`；`devDependencies` 也不含任何测试框架（无 Vitest / Jest）。如需引入，建议后续添加 Vitest。

---

## 4. 生产部署

### 4.1 前端构建

```bash
cd frontend
npm run build
```

构建命令为 `vue-tsc -b && vite build`：先做 TypeScript 类型检查，再由 Vite 打包。产物输出到 `frontend/dist/`。`exceljs` 通过 `manualChunks` 单独分包（见 `vite.config.ts`）。

### 4.2 后端生产启动

```bash
cd backend

# 生产启动（不带 --reload）
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 多 worker（按需）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

> 多 worker 注意：`init_rules_db()` 在每个 worker 的 lifespan 中都会执行一次，但因其幂等（先查空再插），多 worker 并发首次启动存在极小概率重复插入默认规则。单 worker 部署无此问题。

确保 `.env` 已正确配置（尤其 `DATA_PATH` 指向生产数据目录、`DEBUG=false`）。

### 4.3 Nginx 反代示例

前端静态资源由 Nginx 直接服务，`/api` 反代到后端 8000 端口：

```nginx
server {
    listen       80;
    server_name  your.domain.com;

    # 前端静态产物
    root  /opt/cpq/frontend/dist;
    index index.html;

    # SPA history 路由回退
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反代到后端
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # 文件上传/导出可能较大
        client_max_body_size 50m;
        proxy_read_timeout   120s;
    }

    # 静态资源缓存
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

> 前端所有 API 请求均走 `/api` 前缀（与后端 router 的 `prefix="/api/..."` 一致），无需额外路径重写。

### 4.4 生产环境变量取值建议

```ini
APP_NAME=CPQ Platform
APP_VERSION=0.1.11
DEBUG=false
DATA_PATH=/data/cpq                    # 生产数据目录（确保 Reference\ 子目录存在且可写）
DATABASE_URL=sqlite:///./data/cpq_platform.db   # 遗留字段，保持默认即可
CORS_ORIGINS=["https://your.domain.com"]        # 收窄到实际前端域名
```

建议用 systemd / Docker 管理后端进程，并保证：
- `DATA_PATH` 指向持久化卷，避免容器/实例重建丢数据；
- `backend/storage/`（文件上传/导出目录）同样持久化。

---

## 5. 排错与常见坑

### 5.1 VM 文件截断 / 同步延迟

在通过 shell / VM（如 `mcp__workspace__bash`）读取本项目文件时，可能读到滞后或截断的内容（文件刚被修改但 VM 视图未同步）。

- **以 Read 工具读取的内容为准**，不要仅凭 bash 的 `cat`/`head` 判断文件实际内容。
- **改后端文件后用 `python -m py_compile` 验证语法**，避免截断导致语法错误未被察觉：
  ```bash
  cd backend && python -m py_compile app/core/config.py app/main.py
  ```

### 5.2 `DATABASE_URL` 遗留字段

`config.py` 中 `DATABASE_URL` 指向 `./data/cpq_platform.db`，但**全代码库无任何处实际使用它**。真正读写的数据在 `DATA_PATH\Reference\` 下的 6 个独立库。若以为改 `DATABASE_URL` 能切换数据库，会被误导。详见 [§2.1](#21-逐项说明)。

### 5.3 解析配置存在两套（rules.db vs 前端 localStorage）

Excel 解析的"区域识别/字段映射"配置存在两处来源，容易混淆：

- **后端 `rules.db`**：`l6_region_config` / `kp_region_config` 表，由 `RulesRepository` 读取，`PricingEngine` 在 `_load_rules()` 中加载（启动时 `init_rules_db()` 灌默认值，前端"规则配置"页可编辑）。
- **前端 localStorage**：`frontend/src/store/parseTemplate.ts` 把解析模板存到 `localStorage.parseTemplates`，在"解析预览/热力图"页面使用。

两套配置互不同步。后端规则影响实际报价解析（`parse_file` / `_parse_items`）；前端 localStorage 主要用于预览交互。调试"解析结果与预期不符"时，务必确认改的是哪一套。

### 5.4 `pricing_engine._load_rules()` 死代码（潜在 AttributeError）

⚠️ **这是一个真实存在的代码缺陷。** 在 `backend/app/engine/pricing_engine.py` 中：

```python
    def _get_business_field_repo(self):
        ...
        return self._business_field_repo

        # ↓ 这两行在 return 之后，属于 unreachable code（死代码）
        # Load rules from DB (with hardcoded fallbacks)
        self._load_rules()
```

`_load_rules()` 本应在 `__init__` 中被调用以初始化 `self._l6_region_config`、`self._kp_region_config`、`self._mb_mappings`、`self._kp_cat_map`、`self._l6_match_dims` 等实例属性。但由于它被错误地缩进进了 `_get_business_field_repo()` 方法体内、且位于 `return` 之后，**永远不会执行**。

后果：当 `PricingEngine` 实例调用 `parse_file()`（处理有效 Sheet 时）、`preview_parse()`、`_parse_items()`、`_extract_meta()`、`match_l6_total()` 等方法时，会因访问未初始化的 `self._l6_region_config` 等而抛出 `AttributeError`。

- **测试为何"通过"**：`test_parse_file_empty_dict` 传空字典不触发内部方法；其余用例因 mock 数据恰好绕开部分属性访问。
- **修复方向**：把 `self._load_rules()` 调用移回 `__init__` 末尾（与其它 `self.xxx = ...` 同级缩进）。

> 排查上传解析、L6 匹配等功能异常时，优先确认是否命中此问题。

### 5.5 CORS 跨域配置

- 开发环境默认放行 `localhost:5173` / `127.0.0.1:5173`，配合 Vite dev server（端口 5173，proxy `/api` → `localhost:8000`）。
- `allow_credentials=False`：当前不支持 Cookie 跨域。后端无认证机制，目前无影响；引入认证后需同步调整。
- 生产部署若前后端不同域，必须在 `.env` 的 `CORS_ORIGINS` 中加入前端实际来源（JSON 数组格式），否则浏览器会拦截 API 请求。

### 5.6 `DATA_PATH` 目录不存在时的行为

`models/base.py` 仅拼接路径，不创建目录：

```python
DATA_DIR = os.path.join(get_settings().DATA_PATH, "Reference")
KP_DB_PATH = os.path.join(DATA_DIR, "kp_data.db")
kp_engine = create_engine(f"sqlite:///{KP_DB_PATH}", ...)
```

- 若 `DATA_PATH\Reference\` 目录不存在，SQLite 在首次连接时**无法自动创建多级目录**，会抛出 `sqlite3.OperationalError: unable to open database file`。
- 启动时 `init_rules_db()` 会率先尝试在 `rules_engine` 上 `create_all`，此时即触发该错误，导致应用启动失败。

**首次部署务必先手动创建该目录**：

```bash
# Windows
mkdir D:\Quotation_Automation\Reference

# Linux
mkdir -p /data/cpq/Reference
```

对比：文件存储目录 `backend/storage/` 由 `FileStorage.__init__` 的 `mkdir(parents=True, exist_ok=True)` 自动创建，无需手动处理。

### 5.7 `create_all` 的"冗余空表"现象

由于所有 ORM 模型共享同一个 `Base.metadata`，而 startup 对 `rules_engine`、`l6_history_engine` 调用 `create_all` 时，会把**所有已导入的表**都建到这两个库里（包括 opportunities、quotations、business_fields 等）。这不会影响功能（各 repo 只读写自己库里的表），但会让 `rules.db` / `l6_history.db` 里出现一批永远为空的表。属设计层面的瑕疵，排错时知晓即可，无需手动清理。

---

## 附：快速启动清单

```
[ ] 1.  Python 3.11+ / Node 18+ 已安装
[ ] 2.  cd backend && pip install -r requirements.txt
[ ] 3.  cd frontend && npm install
[ ] 4.  创建 backend/.env（至少设置 DATA_PATH）
[ ] 5.  手动创建 DATA_PATH\Reference\ 目录
[ ] 6.  从旧环境复制 kp_data.db / l6_data.db，或手动建表 + 录入基础数据
[ ] 7.  cd backend && uvicorn app.main:app --reload --port 8000   # 后端
[ ] 8.  cd frontend && npm run dev                                  # 前端(5173)
[ ] 9.  浏览器访问 http://localhost:5173
```
