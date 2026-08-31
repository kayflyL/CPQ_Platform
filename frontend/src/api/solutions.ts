/** 解决方案 API（对接 /api/solutions）。 */
import axios from 'axios'
const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface SolutionPlatform { name: string; spec: string; link?: string }
export interface SolutionScene { key: string; label: string }
export interface Solution {
  id?: number
  key: string
  scene_key: string
  scene: string
  title: string
  sub?: string
  features: string[]
  intro?: string
  content_md?: string
  platforms: SolutionPlatform[]
  created_at?: string | null
  updated_at?: string | null
}

export const solutionApi = {
  list: (params?: { scene_key?: string }) =>
    RESP<{ solutions: Solution[] }>(axios.get('/api/solutions/', { params })),
  get: (key: string) => RESP<Solution>(axios.get(`/api/solutions/${key}`)),
  scenes: () => RESP<{ scenes: SolutionScene[] }>(axios.get('/api/solutions/scenes')),
  create: (data: Partial<Solution> & { key: string; scene_key: string; scene: string; title: string }) =>
    RESP<Solution>(axios.post('/api/solutions/', data)),
  update: (key: string, data: Partial<Solution>) =>
    RESP<Solution>(axios.put(`/api/solutions/${key}`, data)),
  remove: (key: string) => RESP<{ success: boolean }>(axios.delete(`/api/solutions/${key}`)),
}
