/**
 * system_config 动态选项 wrapper（对接 /api/system-config）。
 * repo 对 dict/list 自动 json 序列化；GET /{key}/value 返回 {key, value}，value 已反序列化。
 */
import axios from 'axios'

const RESP = <T>(p: Promise<{ data: T }>) => p.then(r => r.data)

export interface SystemConfigItem {
  key: string
  value: any
  type?: string
  description?: string
}

export interface OptionItem {
  value: string
  label: string
}

export const systemConfigApi = {
  list: () => RESP<SystemConfigItem[]>(axios.get('/api/system-config/')),
  get: (key: string) =>
    RESP<SystemConfigItem>(axios.get(`/api/system-config/${encodeURIComponent(key)}`)),
  getValue: <T = any>(key: string) =>
    RESP<{ key: string; value: T }>(
      axios.get(`/api/system-config/${encodeURIComponent(key)}/value`)
    ).then(r => r.value as T),
  getRequirementSlotsSpec: () =>
    RESP<{ slots: any[]; version: number; ask_threshold: number }>(
      axios.get('/api/system-config/requirement_slots_spec')
    ),
  getSkillPromptsEffective: () =>
    RESP<{ key: string; value: Record<string, any> }>(
      axios.get('/api/system-config/skill_prompts/effective')
    ).then(r => r.value),
  listSkillPrompts: () =>
    RESP<{ items: any[] }>(axios.get('/api/system-config/skill-prompts')).then(r => r.items),
  updateSkillPrompt: (slotKey: string, payload: { template: string; name?: string; enabled?: boolean }) =>
    RESP<any>(axios.put(`/api/system-config/skill-prompts/${encodeURIComponent(slotKey)}`, payload)),

  set: (key: string, value: any, type?: string, description?: string) =>
    RESP<SystemConfigItem>(
      axios.put(`/api/system-config/${encodeURIComponent(key)}`, { value, type, description })
    ),
  delete: (key: string) =>
    RESP<{ success: boolean }>(axios.delete(`/api/system-config/${encodeURIComponent(key)}`)),
}
