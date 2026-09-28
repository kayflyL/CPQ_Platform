/**
 * 方案助手壳层开关（模块级单例）。
 *
 * 浮动助手面板由 DefaultLayout 持有渲染（AssistantPanel + FAB），但工作台磁贴、
 * 全屏入口等多处需要「唤起/收起」它——把 open 状态提升到这里共享，任意入口写
 * 同一个 ref，面板只挂一处。
 */
import { ref } from 'vue'

const open = ref(false)

export function useAssistantShell() {
  function show() { open.value = true }
  function hide() { open.value = false }
  function toggle() { open.value = !open.value }
  return { open, show, hide, toggle }
}
