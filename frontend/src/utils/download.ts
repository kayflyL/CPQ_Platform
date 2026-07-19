/**
 * 触发浏览器下载一个 Blob（避免在多处复制 createObjectURL + <a> + revoke 模板）
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // 释放 URL，避免内存泄漏
  window.URL.revokeObjectURL(url)
}
