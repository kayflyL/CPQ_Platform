import { message } from 'ant-design-vue'

/** 复制文本到剪贴板（Clipboard API 优先，失败回落 execCommand）。
 *  absolute=true 时站内相对路径自动补全为绝对 URL（站外也能直接用）。 */
export async function copyText(
  text: string,
  opts: { absolute?: boolean; successMsg?: string } = {},
): Promise<boolean> {
  const full = opts.absolute && !/^https?:/.test(text) ? location.origin + text : text
  try {
    await navigator.clipboard.writeText(full)
    message.success(opts.successMsg || '已复制')
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = full
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    if (ok) message.success(opts.successMsg || '已复制')
    return ok
  }
}
