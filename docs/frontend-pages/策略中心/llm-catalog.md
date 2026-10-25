# 模型与参数库（选型配置页·「模型与参数库」模式）

> 最后更新：2026-09-27
>
> 落点变更：v1 曾是策略中心门户独立卡+独立路由(/strategies/llm-catalog)——用户裁定应归入选型配置且三表不该一页堆积。现为
> **选型配置页顶栏模式开关的第四个模式**（[SelectionWorkspace](../../../frontend/src/views/admin/selection/SelectionWorkspace.vue)），页内 **a-tabs 三页签**：大模型库 / 推理框架库 / 场景参数。独立路由已删除。

组件：[LlmCatalogAdmin](../../../frontend/src/views/admin/strategy/LlmCatalogAdmin.vue)（行编辑，admin-card-pattern）。

## 三张参考库

| 页签 | 表 | 字段要点 |
|---|---|---|
| 大模型库 | `rules.llm_models` | 公司/模型/参数量/注意力(GQA·MHA·MLA)/结构四参数(hidden·layers·heads·kv_heads)/原生ctx/实测大小/置信度；**结构四参数缺一不可算**（KV 公式必需）；vendor+name 唯一 |
| 推理框架库 | `rules.inference_frameworks` | 4/8/16bit 量化系数 + 每卡额外开销 GB + 张量并行开关；**系数进表不写死**，改即生效（vLLM 为主推行） |
| 场景参数 | `rules.scene_params` | 场景名/推荐上下文/最低速度/需多模态 |

## 与配置器的关系

- 配置器选择器数据来自 `/api/gpu-sizing/catalog`，计算 `/solve`；本页改框架系数/场景参数，配置器下一次计算即生效。
- 首版数据 = Excel v10 首版导入（`backend/scripts/import_llm_catalog_v10.py`，dry_run→确认→upsert），本页做日常增删改。

后端端点：`/api/gpu-sizing/admin/{models,frameworks,scenes}`（GET/POST/PUT/DELETE），见 `backend/app/api/gpu_sizing_api.py`。
