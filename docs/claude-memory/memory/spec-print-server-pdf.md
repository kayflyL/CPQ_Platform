---
name: spec-print-server-pdf
description: 规格书打印定式：服务端 Playwright 直出 PDF 下载（printExport.ts→/api/spec-templates/print-pdf），浏览器另存为PDF命名靠document.title且含/即失效
metadata:
  node_type: memory
  type: project
  originSessionId: 8ab9e082-4aa2-483c-8b98-f495113e7978
  modified: 2026-09-30T03:37:18.500Z
---

2026-09-30 定式：三处规格书打印（SpecTemplateEditor / quote Workspace / ConfigWizard）统一走「前端序列化打印态 DOM → POST /api/spec-templates/print-pdf → 后端 render_print_pdf（Playwright, prefer_css_page_size 吃文档自身 @page A4+14mm）→ Content-Disposition 中文文件名直接下载」；后端 playwright 缺失时回退 window.print()（旧路径：临时改 document.title 当文件名）。

**根因教训**：Edge/Chrome「另存为 PDF」建议文件名取 document.title，标题含 `/`（旧 buildPrintTitle 的 `toLocaleDateString('zh-CN')` 日期=2026/9/30）等非法字符时被弃用，退回 URL 最后一段命名 → 用户拿到 `edit.htm`（路由 /export-templates/spec/:id/edit）。文件名必须过 `sanitizeFilename`（`\/:*?"<>|` → `-`），日期用 `-` 分隔。

**关键实现**：`frontend/src/utils/printExport.ts`（buildPrintTitle/serializePrintDocument/exportSpecPdf）；序列化=clone documentElement+剥离全部 script（防 SPA 在服务端重跑）+注入 `<base href=document.baseURI>`（样式/图片按前端源站解析）+写 `<title>`（进 PDF 元数据）。打印版式由 SpecSheet.vue 非 scoped `@media print` + `@page{size:A4;margin:14mm}` 驱动，page.pdf 与浏览器对话框同一套 CSS，勿再传 margin 参数（会叠加）。三个调用方 overlay 结构统一 `.spec-sheet-overlay > .spec-sheet-scroll > SpecSheet.spec-sheet-root`。

验证方式：preview 起 backend-verify(8010 关鉴权)+frontend-verify(5174)，动态 `import('/src/utils/printExport.ts')` 在真实 SPA 页面上序列化+fetch POST，看 200/application/pdf + Content-Disposition。playwright 只在 backend/.venv 有（全局 python 没有，PATH 上的 python 是 hermes 运行时）。碰规格书打印/PDF 导出前先看。
