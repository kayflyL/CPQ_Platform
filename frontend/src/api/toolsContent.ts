/** 工具内容 API（/api/tools/content）—— 工具中心/工具页展示文案的读写。
 *  读=登录即可；写=action.tools.content.manage（默认仅 admin）。content 为不透明 JSON blob。 */
import axios from 'axios'
import type { ToolContent } from '@/constants/toolsRegistry'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export const toolsContentApi = {
  list: () => RESP<{ contents: Record<string, ToolContent>; defaults: Record<string, ToolContent> }>(
    axios.get('/api/tools/content'),
  ),
  save: (key: string, content: ToolContent) =>
    RESP<{ success: boolean }>(axios.put(`/api/tools/content/${encodeURIComponent(key)}`, { content })),
}
