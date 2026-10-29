---
name: canonical-field-labels
description: 商机/字段规范中文标签的权威来源：backend/scripts/init_business_fields.py 种子
metadata: 
  node_type: memory
  type: reference
  originSessionId: 34910a15-c69f-401d-bd3a-ef2f91adfb85
  modified: 2026-07-26T04:59:28.971Z
---

商机相关字段的**规范中文标签**权威来源是 `backend/scripts/init_business_fields.py` 的 `fields_data` 种子（约 32 个字段定义）。详情页 `OpportunityDetail.vue` 的 infoFields 是**动态**从 business_fields 表读取的（`loadInfoFields`），只有读不到时才用组件内 fallback；所以用户在详情页实际看到的标签 = 这个种子。

已确认的规范名（勿在列表/表格里另造新词）：
- `customer_name` → 客户名称
- `sales_person` → **销售人员**（不是"对接销售"/"业务/销售"，后两者一个是旧列表旧名、一个是组件兜底）
- `fae` → FAE
- `platform_type` → **平台类型**（不是"硬件平台"）
- `chassis_form` → **机箱形态**（不是"机箱规格"/"机箱"）

不在种子里的运行时/计算字段，沿用其他页面已有叫法：
- `purchase_qty` → 采购数量（详情页 fallback + RecycleBin 一致）
- `config_count` → 配置数（RecycleBin 列名）
- `created_at` → 创建时间（列头）

**How to apply:** 凡是给商机/报价字段起列名、筛选项、表头、导出列名，先以种子为准；种子没有的再查 RecycleBin.vue / OpportunityDetail.vue 复用，禁止凭直觉新造中文标签——用户对命名一致性很敏感（见 [[systematic-cleanup-not-whackamole]]）。

相关：antd-vue 表格列必须写 `dataIndex` 才会渲染单元格数据（只写 `key` 不绑数据 → 空列）。RecycleBin.vue 是范本，OpportunityList 曾因漏 dataIndex 整列空白。

**补充（2026-07-26 踩坑）：** business_fields 表的数据**不止**来自 init_business_fields.py 种子——「字段管理」(BusinessFieldManagement) 运行时也会往里加字段（如 industry/customer_type 最初即由此加入，source_column=NULL 走 extra_fields JSON）。所以：
- 现有库可能含种子外的字段（光看种子会漏）
- 详情页字段显示靠 `used_in_pages`（`getFieldsByPage('opportunity_detail')` API，位于 fields.ts），不是种子里有就自动显示——要让新字段出现在详情页，得在字段管理勾选其 used_in_pages 含 `opportunity_detail`
- 给现有库补字段定义走 `scripts/seed_*.py` 幂等补录（init 种子有 existing>0 跳过逻辑，不会自动补老库）
- `/api/opportunities/field-history/{key}` 要求字段已注册 business_fields，否则 400
