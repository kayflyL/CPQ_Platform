import { ref } from 'vue'
import { portalApi } from '@/api/portal'

export const ASSIGNEE_REQUIRED_DETAIL = '下游处理人未配置，请选择'

export function useDownstreamAssignee() {
  const pickerOpen = ref(false)
  const pickerTitle = ref('')
  const pickerOptions = ref<string[]>([])
  const pickerChosen = ref('')
  const pending = ref<((name: string) => void) | null>(null)

  async function promptAssignee(nodeKey: string, label: string, onConfirm: (name: string) => void) {
    pickerTitle.value = label
    pickerChosen.value = ''
    let list: string[] = []
    try {
      const res = await portalApi.assignOptions()
      list = res.assignees?.[nodeKey] || []
    } catch {
      list = []
    }
    pickerOptions.value = list
    pending.value = onConfirm
    pickerOpen.value = true
  }

  function confirmPicker() {
    const cb = pending.value
    pending.value = null
    pickerOpen.value = false
    if (cb && pickerChosen.value) cb(pickerChosen.value)
  }

  function cancelPicker() {
    pending.value = null
    pickerOpen.value = false
  }

  return { pickerOpen, pickerTitle, pickerOptions, pickerChosen, promptAssignee, confirmPicker, cancelPicker }
}
