# Changelog

## 2026-07-18

### 字段管理优化
- **入口迁移**：字段管理从独立页面移至导出模板列表页，通过右侧抽屉访问
- **分类精简**：删除 l6（8个）、kp（4个）、config（1个）分类，保留 opportunity/item/system/dynamic
- **命名对齐**：
  - `item_profit_margin` label 改为"利润率"（对齐前端 UI）
  - 重加 `cfg_unit_price`/`cfg_total_price` 静态字段，支持 config_summary 数组绑定
  - 动态字段分组显示名映射：config_summary→配置汇总, l6_details→L6配置项, kp_details→KP配置项
- **功能精简**：移除 permission 列、enabled 列、批量操作、校验规则/依赖条件表单
- **后端精简**：注释 13 个废弃端点，保留 6 个核心端点；`list_business_fields` 移除 inspect 扫描

### 涉及文件
- `frontend/src/views/univer/UniverTemplateList.vue`
- `frontend/src/views/admin/BusinessFieldManagement.vue`
- `frontend/src/layouts/DefaultLayout.vue`
- `frontend/src/router/index.ts`
- `backend/app/api/admin.py`
- `backend/app/services/template_filler.py`
