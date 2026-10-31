// 办公室档案（v4 第 2 步，2026-10-31）：「办公室」= 一个业务系统的档案袋。
// 全局单例状态：办公室清单（后端 system_config.ai_colleagues.offices 下发）+
// 当前办公室（localStorage 记忆）+ 按档案过滤的四类引用（角色/房间/工作流/工具）。
// 清单 null = 不限（现有全部，CPQ办公室即此态）；数组 = 白名单（可含尚未接入的 id）。
import { computed, ref } from 'vue'
import type { OfficeProfile } from '@/api/office'

const _STORAGE_KEY = 'cpq.officeKey'

const offices = ref<OfficeProfile[]>([])
const currentKey = ref<string>(localStorage.getItem(_STORAGE_KEY) || 'cpq')

export type OfficeScope = 'role' | 'room' | 'flow' | 'tool'

export function useOfficeProfile() {
  const current = computed(() =>
    offices.value.find((o) => o.key === currentKey.value) || offices.value[0] || null,
  )

  function setOffices(list: OfficeProfile[] | undefined | null) {
    offices.value = Array.isArray(list) && list.length ? list : []
    if (offices.value.length && !offices.value.some((o) => o.key === currentKey.value)) {
      currentKey.value = offices.value[0].key
    }
  }

  function switchOffice(key: string) {
    if (!offices.value.some((o) => o.key === key)) return
    currentKey.value = key
    localStorage.setItem(_STORAGE_KEY, key)
  }

  /** 该 id 是否属于当前办公室：清单为 null=不限；数组=白名单（可含尚未接入的 id）。 */
  function inOffice(scope: OfficeScope, id: string): boolean {
    const profile = current.value
    if (!profile) return true
    const list = scope === 'role' ? profile.role_keys
      : scope === 'room' ? profile.room_ids
        : scope === 'flow' ? profile.flow_keys
          : profile.tool_names
    if (list == null) return true
    return list.includes(id)
  }

  return { offices, currentKey, current, setOffices, switchOffice, inOffice }
}
