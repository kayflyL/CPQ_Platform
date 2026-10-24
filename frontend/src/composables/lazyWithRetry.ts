/** defineAsyncComponent + 失败自动重试。
 * 为什么：dev 服务器热编译窗口 / 弱网时，异步 chunk 首次加载会失败，
 * 默认行为是白屏卡死（需求单弹窗空白踩坑）；这里自动重试 2 次，仍失败才走 error。 */
import { defineAsyncComponent, type Component } from 'vue'

export function lazyWithRetry(loader: () => Promise<Component>, delay = 200) {
  return defineAsyncComponent({
    loader,
    delay,
    onError(_error, retry, fail, attempts) {
      if (attempts <= 2) retry()
      else fail()
    },
  })
}
