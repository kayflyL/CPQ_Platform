/**
 * 规格书打印导出（服务端 Playwright PDF 直下）
 *
 * 浏览器「另存为 PDF」的建议文件名取自 document.title，标题不可用
 * （含 / 等非法字符，或个别 Edge 版本不认 SPA 标题）时会退回用 URL
 * 最后一段命名（如 /export-templates/spec/3/edit → edit.htm）。
 * 这里改为：把打印态 DOM（含全部样式、@media print 规则照常生效）送到
 * 后端 Playwright 出 PDF，以确定的文件名直接下载；后端不可用时调用方
 * 再回退浏览器打印对话框。
 */
import { specTemplateApi } from '@/api/specTemplate'

/** Windows 文件名禁字符（\/:*?"<>|）统一替换为 -，首尾空白/点去掉 */
function sanitizeFilename(s: string): string {
  return s.replace(/[\\/:*?"<>|]/g, '-').replace(/^[\s.]+|[\s.]+$/g, '').trim()
}

/** 打印文件名：文档标题 - 公司名 - 日期（日期用 - 分隔，不能用 / ——见文件头注释） */
export function buildPrintTitle(branding?: { doc_title?: string; company_name?: string } | null): string {
  const d = new Date()
  const date = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
  const raw = [branding?.doc_title || '规格书', branding?.company_name, date]
    .filter((s) => s && String(s).trim())
    .join('-')
  return sanitizeFilename(raw) || '规格书'
}

/** 序列化当前文档为可离线渲染的打印 HTML：剥离脚本（防止 SPA 在服务端重跑）、
 *  补 <base>（相对路径的样式/图片按前端源站解析）、写标题（进 PDF 元数据）。
 *  打印态由 @media print 规则驱动，Teleport 到 body 的 .spec-sheet-overlay 已在克隆内。 */
export function serializePrintDocument(title: string): string {
  const root = document.documentElement.cloneNode(true) as HTMLElement
  root.querySelectorAll('script').forEach((el) => el.remove())
  root.querySelectorAll('link[rel="modulepreload"]').forEach((el) => el.remove())
  const head = root.querySelector('head')
  if (head) {
    head.querySelectorAll('base').forEach((el) => el.remove())
    const base = document.createElement('base')
    base.setAttribute('href', document.baseURI)
    head.insertBefore(base, head.firstChild)
    let titleEl = head.querySelector('title')
    if (!titleEl) {
      titleEl = document.createElement('title')
      head.appendChild(titleEl)
    }
    titleEl.textContent = title
  }
  return '<!DOCTYPE html>' + root.outerHTML
}

/** 规格书打印：先走服务端 Playwright PDF（文件名确定），失败抛错由调用方回退 window.print。
 *  调用前需已把打印 overlay 渲染进 DOM（printMode/specVisible = true + nextTick + fitPagesForPrint）。 */
export async function exportSpecPdf(title: string): Promise<void> {
  const res = await specTemplateApi.printPdf({ title, html: serializePrintDocument(title) })
  const url = URL.createObjectURL(res)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title}.pdf`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
