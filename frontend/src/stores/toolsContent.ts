/**
 * 工具内容 Pinia Store —— rules.tool_contents 的前端缓存。
 * 展示端一律走 of(key)（DB 内容浅合并注册表默认值，顶层字段级覆盖）；
 * 编辑器保存后写回缓存，工具中心/工具页即时刷新。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { toolsContentApi } from '@/api/toolsContent'
import { TOOLS, type ToolContent } from '@/constants/toolsRegistry'

const _defaultsByKey = Object.fromEntries(TOOLS.map(t => [t.key, t.defaultContent]))

export const useToolsContentStore = defineStore('toolsContent', () => {
  const contents = ref<Record<string, ToolContent>>({})
  const loaded = ref(false)
  let _promise: Promise<void> | null = null

  /** 拉取工具内容（幂等；DB 故障降级为注册表默认值，不阻塞页面）。 */
  async function ensure(): Promise<void> {
    if (loaded.value) return
    if (!_promise) {
      _promise = toolsContentApi.list()
        .then(r => {
          // defaults 以 DB 种子为准（后端 repo 与前端常量同源），空表时兜底
          contents.value = { ...(r.defaults || {}), ...(r.contents || {}) }
        })
        .catch(() => { contents.value = {} })
        .finally(() => { loaded.value = true })
    }
    return _promise
  }

  /** 某 key 的生效内容 = DB 内容覆盖注册表默认（顶层字段级；编辑器永远存完整 blob）。 */
  function of(key: string): ToolContent {
    return { ..._defaultsByKey[key], ...(contents.value[key] || {}) } as ToolContent
  }

  /** 编辑器保存：写库并刷新缓存。 */
  async function save(key: string, content: ToolContent): Promise<void> {
    await toolsContentApi.save(key, content)
    contents.value[key] = content
  }

  return { contents, loaded, ensure, of, save }
})
