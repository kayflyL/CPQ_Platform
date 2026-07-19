# 前端 TypeScript 构建错误清单

> 生成时间：2026-07-18

## 汇总

共 **20 个**错误，分布在 8 个文件中。

| 错误类型 | 数量 |
|---------|------|
| 未使用变量/函数 (TS6133) | 3 |
| 类型不匹配 (TS2322/TS2345) | 6 |
| 属性不存在 (TS2339/TS2353) | 6 |
| 隐式 any 类型 (TS7006) | 5 |

---

## 1. `src/utils/excel-generator.ts`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 249 | TS6133 | `applyCellStyle` 函数已声明但未使用 |

## 2. `src/views/admin/BasePricing.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 283 | TS2322 | `detailChartData` 可能为 `null`，不能赋值给 `ChartData` 类型 |
| 384 | TS2345 | `removeSpec(idx)` 参数 `string \| number` 不能赋值给 `number` |

## 3. `src/views/ExcelParser.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 105 | TS2345 | `getCellClass(rIdx, cIdx)` 参数 `string \| number` 不能赋值给 `number` |
| 106 | TS2345 | `getCellTooltip(rIdx, cIdx)` 参数 `string \| number` 不能赋值给 `number` |
| 168 | TS7006 | `items.map((item, idx) => ...)` 参数 `item` 隐式 `any` |
| 168 | TS7006 | `items.map((item, idx) => ...)` 参数 `idx` 隐式 `any` |

## 4. `src/views/opportunity/OpportunityDetail.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 177 | TS2339 | `platform_type` 属性不存在于报价类型定义 |
| 265 | TS2339 | `platform_type` 属性不存在于报价类型定义 |
| 358 | TS2305 | `Opportunity` 类型未从 `@/types/opportunity` 导出 |
| 559 | TS2322 | `number` 类型不能赋值给 `string` |
| 629 | TS7006 | 参数 `q` 隐式 `any` |

## 5. `src/views/opportunity/OpportunityList.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 170 | TS2305 | `Opportunity` 类型未从 `@/types/opportunity` 导出 |
| 228 | TS7006 | 参数 `p` 隐式 `any` |
| 334 | TS2353 | `opportunity_name` 属性不存在于类型定义 |

## 6. `src/views/quote/Workspace.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 871 | TS2353 | `detected` 属性不存在于 `WarrantyInfo` 类型 |
| 872 | TS2353 | `detected` 属性不存在于 `WarrantyInfo` 类型 |

## 7. `src/views/univer/UniverTemplateEditor.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 345 | TS6133 | `opportunityApi` 已声明但未使用 |
| 353 | TS6133 | `router` 已声明但未使用 |

## 8. `src/views/univer/UniverTemplateList.vue`

| 行 | 错误码 | 说明 |
|----|--------|------|
| 198 | TS2353 | `'sheet-1'` 属性不存在于 `SheetConfig` 类型 |
