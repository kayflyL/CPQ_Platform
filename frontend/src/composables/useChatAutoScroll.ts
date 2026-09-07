import { nextTick, onScopeDispose, watch, type Ref } from 'vue'

/**
 * 聊天流跟随滚动（Claude Code/ChatGPT 语义）：仅当用户本就在底部时跟随新内容。
 * 用户上翻即停跟（浏览历史不被流式增量拽回底部），滚回底部自动恢复跟随；
 * 发送消息/加载历史等离散事件传 force=true 强制回底。
 */
export function useChatAutoScroll(elRef: Ref<HTMLElement | null>) {
  const NEAR_BOTTOM_PX = 96
  let follow = true

  function distanceFromBottom(el: HTMLElement): number {
    return el.scrollHeight - el.scrollTop - el.clientHeight
  }

  function onScroll() {
    const el = elRef.value
    if (!el) return
    follow = distanceFromBottom(el) <= NEAR_BOTTOM_PX
  }

  // 容器可能随面板展开/收起挂载卸载，模板 ref 变化时重挂监听
  const stopWatch = watch(elRef, (el, prev) => {
    prev?.removeEventListener('scroll', onScroll)
    el?.addEventListener('scroll', onScroll, { passive: true })
    if (el) follow = distanceFromBottom(el) <= NEAR_BOTTOM_PX
  }, { flush: 'post' })

  onScopeDispose(() => {
    stopWatch()
    elRef.value?.removeEventListener('scroll', onScroll)
  })

  async function scrollToBottom(force = false) {
    if (force) follow = true
    else if (!follow) return
    await nextTick()
    const el = elRef.value
    if (el) el.scrollTop = el.scrollHeight
  }

  return { scrollToBottom }
}
