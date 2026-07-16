# 数据库

> 版本：v0.1.11 | 更新日期：2026-07-11

## 数据库总览

所有数据库统一存放在 `{DATA_PATH}/Reference/`（默认 `D:\Quotation_Automation\Reference\`）。其中 5 个由 `base.py` 定义独立的 engine + sessionmaker，`comments.db` 由 `comment_repo.py` 以原生 `sqlite3` 直接管理。各库相互独立，严禁混用。

| 数据库 | 用途 | 管理方式 |
|--------|------|----------|
| `kp_data.db` | KP 零件价格、分类数据；业务字段（business_fields）及其引用、审计、使用统计 | `base.py` engine |
| `l6_data.db` | L6 整机型号、五维匹配记录 | `base.py` engine |
| `opportunities.db` | 商机线索、报价单、报价配置项、商机文件 | `base.py` engine |
| `rules.db` | 业务规则（区域识别、KP 分类映射、主板映射、匹配规则）、导出模板 | `base.py` engine |
| `l6_history.db` | L6 价格变更历史快照 | `base.py` engine |
| `comments.db` | 商机批注 | 原生 sqlite3（`comment_repo.py`） |

Engine / SessionLocal 定义位置：`backend/app/models/base.py`

> 说明：每张表实际写入哪个库，由其 Repository 绑定的 SessionLocal 决定。下文各表的归属均以代码中的 Repository 绑定为准。