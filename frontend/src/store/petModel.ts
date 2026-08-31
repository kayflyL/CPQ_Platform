import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface PetModelDef {
  key: string
  label: string
  path: string
}

/** 桌宠虚拟形象目录：key 与后端白名单一致，路径指向本地 vendor 资源 */
export const PET_MODEL_CATALOG: PetModelDef[] = [
  { key: 'koharu', label: 'Koharu 红发少女', path: '/live2d/koharu/assets/koharu.model.json' },
  { key: 'hibiki', label: 'Hibiki 音羽', path: '/live2d/hibiki/assets/hibiki.model.json' },
  { key: 'shizuku', label: 'Shizuku 白裙', path: '/live2d/shizuku/assets/shizuku.model.json' },
  { key: 'nico', label: 'Nico 妮可', path: '/live2d/nico/assets/nico.model.json' },
  { key: 'izumi', label: 'Izumi 泉水', path: '/live2d/izumi/assets/izumi.model.json' },
]

/** 无指定角色时的兜底形象（新同事默认值） */
export const DEFAULT_PET_MODEL = 'koharu'

export function petModelPath(key?: string | null): string {
  const hit = PET_MODEL_CATALOG.find((m) => m.key === key)
  return hit?.path || PET_MODEL_CATALOG[0].path
}

export function isPetModelKey(key?: string | null): boolean {
  return !!key && PET_MODEL_CATALOG.some((m) => m.key === key)
}

/**
 * 桌宠形象状态：形象按「AI 同事角色」统一，由员工页在同事身份上维护 pet_model。
 * 这里只作为「当前活跃角色的形象」通道：聊天面板把当前角色 + 该角色 pet_model 写进来，
 * 悬浮宠物据此渲染；无角色时落到默认兜底形象。
 */
export const usePetModelStore = defineStore('petModel', () => {
  const activeRoleKey = ref<string | null>(null)
  const activePetModel = ref<string>(DEFAULT_PET_MODEL)

  function setActive(roleKey: string | null, petModel?: string | null) {
    activeRoleKey.value = roleKey
    activePetModel.value = isPetModelKey(petModel) ? petModel! : DEFAULT_PET_MODEL
  }

  return { activeRoleKey, activePetModel, setActive }
})
