/**
 * 产出物分享 API（网盘式）— 生成/列表/撤销 + 免登录链接。
 * 分享 = 渲染落盘 xlsx + 免登录 token 下载；视角 = 同一模板的信息维度。
 */
import axios from 'axios'

export type ShareSourceType = 'quote' | 'cost' | 'scheme'
export type ShareView = 'scheme' | 'cost' | 'customer'

export interface ArtifactShare {
  id: number
  token: string
  opportunity_id: string
  source_type: string
  source_id: string
  title: string
  view: string
  filename: string
  has_extract_code: boolean
  expires_at: string
  revoked_at: string
  download_count: number
  last_download_at: string
  created_by: string
  created_at: string
}

export interface SharePreviewResult {
  kind: 'univer'
  workbook_snapshot: Record<string, any>
}

const oppBase = (oppId: string) => `/api/portal/opp/${encodeURIComponent(oppId)}`

export const artifactShareApi = {
  /** 生成分享（渲染落盘 + 归档附件桶 + 建 token） */
  async create(oppId: string, body: {
    source_type: ShareSourceType
    source_id: string | number
    view: ShareView
    template_id?: number
    expiry_days?: number
    extract_code?: string
  }): Promise<{ share: ArtifactShare; share_path: string }> {
    return (await axios.post(`${oppBase(oppId)}/artifacts/share`, body)).data
  },

  list: async (oppId: string, sourceType: ShareSourceType, sourceId: string | number):
    Promise<{ shares: ArtifactShare[] }> =>
    (await axios.get(`${oppBase(oppId)}/artifacts/shares`, {
      params: { source_type: sourceType, source_id: String(sourceId) },
    })).data,

  revoke: async (oppId: string, shareId: number): Promise<{ share: ArtifactShare }> =>
    (await axios.post(`${oppBase(oppId)}/artifacts/shares/${shareId}/revoke`)).data,

  /** 预览：quote=Univer snapshot；cost/scheme=标准网格 */
  preview: async (oppId: string, params: {
    source_type: ShareSourceType
    source_id: string | number
    view: ShareView
    template_id?: number
  }): Promise<SharePreviewResult> =>
    (await axios.get(`${oppBase(oppId)}/artifacts/share/preview`, { params })).data,

  /** 登录态直接下载（实时生成，不经链接）——返回带参完整 URL（配 fetchAuthedBlob 用） */
  downloadUrl: (oppId: string, params: {
    source_type: ShareSourceType
    source_id: string | number
    view: ShareView
    template_id?: number
  }) => {
    const qs = new URLSearchParams({
      source_type: params.source_type,
      source_id: String(params.source_id),
      view: params.view,
      ...(params.template_id ? { template_id: String(params.template_id) } : {}),
    }).toString()
    return `${oppBase(oppId)}/artifacts/share/download?${qs}`
  },

  downloadParams: (params: {
    source_type: ShareSourceType
    source_id: string | number
    view: ShareView
    template_id?: number
  }) => ({
    source_type: params.source_type,
    source_id: String(params.source_id),
    view: params.view,
    ...(params.template_id ? { template_id: String(params.template_id) } : {}),
  }),

  shareLink: (token: string) => `${location.origin}/api/share/${token}`,
}
