/** 服务器可视化图纸配置 API（对接后端 /api/server-catalog/models/{id}/drawing） */
import axios from 'axios'

export type DrawingViewType = 'top' | 'front' | 'rear'

/** 用户标注区域（viewBox 相对坐标，不存像素） */
export interface DrawingRegion {
  uid: string
  name: string
  region_type: string
  x: number
  y: number
  width: number
  height: number
  remark?: string
}

export type DrawingViewBox = [number, number, number, number]

/** 图层元数据（仅存用户编辑过的图层，键=SVG 元素 id） */
export interface DrawingLayerMeta {
  id: string
  name?: string
  visible?: boolean
  locked?: boolean
  opacity?: number
}

export interface DrawingView {
  svg_url: string
  viewBox: DrawingViewBox | null
  regions: DrawingRegion[]
  layers?: DrawingLayerMeta[]
  /** 上一版图纸（兼容旧数据；新版统一走 history 版本管理） */
  prev?: DrawingView | null
  /** 历史版本（最近 N 个） */
  history?: DrawingVersion[]
}

/** 图纸版本（当前版 / 历史版） */
export interface DrawingVersion {
  id: string
  svg_url: string
  viewBox: DrawingViewBox | null
  regions: DrawingRegion[]
  layers?: DrawingLayerMeta[]
  created_at?: string | null
  is_current?: boolean
  file_exists?: boolean
}

export interface ServerDrawingConfig {
  views: Partial<Record<DrawingViewType, DrawingView | null>>
}

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export const serverDrawingApi = {
  /** 读取机型某视图的图纸配置；未配置返回 null */
  get: (modelId: number, view: DrawingViewType = 'top') =>
    RESP<DrawingView | null>(axios.get(`/api/server-catalog/models/${modelId}/drawing`, { params: { view } })),

  /** 上传 SVG（后端清洗后落盘），返回 url / viewBox / 已有 regions */
  uploadSvg: (modelId: number, view: DrawingViewType, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return RESP<{ url: string; viewBox: DrawingViewBox | null; regions: DrawingRegion[] }>(
      axios.post(`/api/server-catalog/models/${modelId}/drawing?view=${view}`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    )
  },

  /** 保存某视图的标注配置 */
  save: (modelId: number, data: { view: DrawingViewType; viewBox: DrawingViewBox | null; regions: DrawingRegion[]; layers?: DrawingLayerMeta[] | null }) =>
    RESP<{ ok: boolean; view: DrawingView }>(axios.put(`/api/server-catalog/models/${modelId}/drawing`, data)),

  /** 保存编辑后的整份 SVG（服务端清洗落盘，更新 svg_url；不动 regions/layers/prev） */
  saveSvg: (modelId: number, view: DrawingViewType, svg: string) =>
    RESP<{ ok: boolean; url: string; viewBox: DrawingViewBox | null }>(
      axios.put(`/api/server-catalog/models/${modelId}/drawing/svg?view=${view}`, { svg })
    ),

  /** 回退到历史版本（默认最近一版，可指定 version_id；当前版会压入历史） */
  rollback: (modelId: number, view: DrawingViewType = 'top', versionId?: string) =>
    RESP<{ ok: boolean; view: DrawingView }>(
      axios.post(`/api/server-catalog/models/${modelId}/drawing/rollback?view=${view}`, null, {
        params: versionId ? { version_id: versionId } : undefined,
      })
    ),

  /** 版本列表：当前版 + 历史版（从新到旧，标注文件是否存在） */
  listVersions: (modelId: number, view: DrawingViewType = 'top') =>
    RESP<{ versions: DrawingVersion[] }>(
      axios.get(`/api/server-catalog/models/${modelId}/drawing/versions`, { params: { view } })
    ),

  /** 删除一个历史版本（其 SVG 文件若无其他引用则一并清理） */
  deleteVersion: (modelId: number, versionId: string, view: DrawingViewType = 'top') =>
    RESP<{ ok: boolean; removed_files?: number }>(
      axios.delete(`/api/server-catalog/models/${modelId}/drawing/versions/${versionId}`, { params: { view } })
    ),

  /** 删除某视图整张图纸（含全部历史版本，文件一并清理） */
  deleteDrawing: (modelId: number, view: DrawingViewType = 'top') =>
    RESP<{ ok: boolean; removed_files?: number }>(
      axios.delete(`/api/server-catalog/models/${modelId}/drawing`, { params: { view } })
    ),
}
