# 公共组件清单

> 版本：v0.1.11 | 更新日期：2026-07-11

当同一 UI 模块被 2 个以上页面引用时，必须抽取为独立公共组件，禁止复制粘贴代码（设计原则第⑨条）。

---

## 1 多页面共享组件

| 组件                 | 路径                                        | 用途                             | 引用页面                         |
| ------------------ | ----------------------------------------- | ------------------------------ | ---------------------------- |
| ExcelTable         | `components/ExcelTable.vue`               | Excel 表格渲染器（A4 预览、单元格编辑、热力图覆盖） | TemplateEditor               |
| OpportunitySidebar | `components/quote/OpportunitySidebar.vue` | 右侧抽屉（商机文件 + 批注 + 悬浮触发按钮）       | Workspace, OpportunityDetail |
| L6RecordCard       | `components/L6RecordCard.vue`             | L6 整机记录卡片（机型/规格/价格展示）          | Workspace, L6Pricing         |

---

## 2 间接共享组件（由 OpportunitySidebar 承载）

这些组件不直接被页面引用，而是通过 `OpportunitySidebar` 嵌入，实际服务于 Workspace 和 OpportunityDetail 两个页面。

| 组件 | 路径 | 用途 |
|------|------|------|
| OpportunityFiles | `components/quote/OpportunityFiles.vue` | 商机文件管理（拖拽上传/下载/重命名/删除/打开） |
| CommentPanel | `components/CommentPanel.vue` | 商机批注面板（添加/查看/删除批注） |

---

## 3 单页面组件

仅在单个页面中使用的组件，暂未达到抽取阈值（< 2 页面引用）。

| 组件 | 路径 | 用途 | 引用页面 |
|------|------|------|----------|
| L6SpecFilter | `components/L6SpecFilter.vue` | L6 五维规格筛选器（机箱/机型/盘位/PSU/主板下拉） | L6Pricing |

---

## 4 汇总

| 分类 | 数量 |
|------|:--:|
| 多页面共享 | 3 |
| 间接共享（via Sidebar） | 2 |
| 单页面 | 1 |
| **合计** | **6** |
