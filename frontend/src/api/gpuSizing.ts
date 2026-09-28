/** AI 推理配置器 API（对接 /api/gpu-sizing；计算在后端 services/gpu_sizing 纯函数）。 */
import axios from 'axios'
const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface CatalogModel {
  id: number; vendor: string; name: string; params_b: number
  default_bits: number; attn: string; confidence: string; max_ctx?: number | null
}
export interface CatalogScene {
  id: number; name: string; recommend_ctx?: number | null
  min_tok_s?: number | null; need_vision?: boolean
}
export interface Catalog {
  vendors: { vendor: string; models: CatalogModel[] }[]
  scenes: CatalogScene[]
  frameworks: { name: string; default_quant?: string | null }[]
  bits_options: number[]
}

export interface EvalRow {
  id: number; name: string; brand?: string | null
  cap_gb?: number | null; bw_gb_s?: number | null; tdp_w?: number | null
  applicable?: { series?: string[] } | { [k: string]: any } | null
  usable_per_card: number; rec: number | null; min: number | null
  headroom: number; over: boolean; max_ctx: number
  speed_tok_s: number | null; fits: boolean
}
export interface EvalResult {
  model: { id: number; name: string; native_max_ctx?: number | null }
  bits: number; framework: string; tp?: boolean | null
  scene: { recommend_ctx: number; concurrency: number }
  need: { weight_gb: number; vision_gb: number; kv_per_tok_gb: number; kv_at_ctx_gb: number; total_gb: number }
  params: { w0: number; kvt: number; occ: number; vision_gb: number; ctx: number; batch: number; overhead?: number }
  rows: EvalRow[]
  skipped: number
}

const T = { timeout: 12000 }
export const gpuSizingApi = {
  catalog: () => RESP<Catalog>(axios.get('/api/gpu-sizing/catalog', T)),
  evaluate: (q: { model_id: number; bits: number; scene_id: number; concurrency: number; framework?: string }) =>
    RESP<EvalResult>(axios.get('/api/gpu-sizing/evaluate', { params: q, ...T })),
}

// ── 管理面（策略中心·解决方案域：三软库行编辑）──
export interface LlmModelRow {
  id: number; vendor: string; name: string; params_b: number; default_bits: number
  attn: string; confidence: string
  hidden_dim?: number | null; num_layers?: number | null; num_heads?: number | null; kv_heads?: number | null
  vision_gb?: number | null; max_ctx?: number | null; measured_size_gb?: number | null; note?: string | null
}
export interface FrameworkRow {
  id: number; name: string; default_quant?: string | null
  coeff_4bit?: number | null; coeff_8bit?: number | null; coeff_16bit?: number | null
  tensor_parallel?: boolean; overhead_gb?: number | null
  kv_cache_note?: string | null; note?: string | null
}
export interface SceneRow {
  id: number; name: string; recommend_ctx?: number | null
  min_tok_s?: number | null; need_vision?: boolean
}

export const gpuCatalogAdminApi = {
  models: () => RESP<{ models: LlmModelRow[] }>(axios.get('/api/gpu-sizing/admin/models')),
  createModel: (d: Partial<LlmModelRow>) => RESP<{ ok: boolean }>(axios.post('/api/gpu-sizing/admin/models', d)),
  updateModel: (id: number, d: Partial<LlmModelRow>) => RESP<{ ok: boolean }>(axios.put(`/api/gpu-sizing/admin/models/${id}`, d)),
  removeModel: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/gpu-sizing/admin/models/${id}`)),
  frameworks: () => RESP<{ frameworks: FrameworkRow[] }>(axios.get('/api/gpu-sizing/admin/frameworks')),
  createFramework: (d: Partial<FrameworkRow>) => RESP<{ ok: boolean }>(axios.post('/api/gpu-sizing/admin/frameworks', d)),
  updateFramework: (id: number, d: Partial<FrameworkRow>) => RESP<{ ok: boolean }>(axios.put(`/api/gpu-sizing/admin/frameworks/${id}`, d)),
  removeFramework: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/gpu-sizing/admin/frameworks/${id}`)),
  scenes: () => RESP<{ scenes: SceneRow[] }>(axios.get('/api/gpu-sizing/admin/scenes')),
  createScene: (d: Partial<SceneRow>) => RESP<{ ok: boolean }>(axios.post('/api/gpu-sizing/admin/scenes', d)),
  updateScene: (id: number, d: Partial<SceneRow>) => RESP<{ ok: boolean }>(axios.put(`/api/gpu-sizing/admin/scenes/${id}`, d)),
  removeScene: (id: number) => RESP<{ ok: boolean }>(axios.delete(`/api/gpu-sizing/admin/scenes/${id}`)),
}
