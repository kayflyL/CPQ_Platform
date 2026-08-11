/** 服务器可视化图纸配置 API（对接后端 /api/server-catalog/models/{id}/drawing） */
import axios from 'axios'
import type { AnatomyRegionKind } from '@/constants/serverAnatomy'

export type DrawingViewType = 'top' | 'front' | 'rear'

/** 用户标注区域（viewBox 相对坐标，不存像素） */
export interface DrawingRegion {
  uid: string
  name: string
  region_type: AnatomyRegionKind
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
  /** 上一版图纸（替换/回退用）；存在时界面可提供「回退」 */
  prev?: DrawingView | null
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

  /** 回退到上一版图纸（当前与 prev 互换，再点一次可切回） */
  rollback: (modelId: number, view: DrawingViewType = 'top') =>
    RESP<{ ok: boolean; view: DrawingView }>(
      axios.post(`/api/server-catalog/models/${modelId}/drawing/rollback?view=${view}`)
    ),
}
