/** 服务器3D模型管理 API(对接后端 /api/server-3d-models)。 */
import axios from 'axios'

export interface Server3dModel {
  id: number
  name: string
  /** 绑定的机型id列表(多对多):绑定即上架,清空即隐藏 */
  model_ids: number[]
  /** 前端不透明JSON字符串(布局/分区标注覆盖),后端整存整取 */
  layout_config: string | null
  created_at?: string | null
  updated_at?: string | null
}

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export const server3dApi = {
  list: () => RESP<{ models: Server3dModel[] }>(axios.get('/api/server-3d-models/')).then(r => r.models),
  getByModel: (modelId: number) =>
    RESP<Server3dModel | null>(axios.get(`/api/server-3d-models/by-model/${modelId}`)),
  update: (id: number, data: Partial<Server3dModel>) =>
    RESP<{ ok: boolean }>(axios.put(`/api/server-3d-models/${id}`, data)),
  remove: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/server-3d-models/${id}`)),
}
