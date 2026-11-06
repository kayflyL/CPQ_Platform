<script setup lang="ts">
/** 工具页壳（/tools/:toolId）—— 面包屑 + 标题/页签 + 可编辑说明区 + 导流条。
 *  页签内是注册表登记的现有页面组件（原样迁入零改动）；说明区/导流文案来自
 *  toolsContent store（后台编辑器维护）。「去后台编辑」仅持 action.tools.content.manage 者可见。 */
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { TOOLS } from '@/constants/toolsRegistry'
import { useToolsContentStore } from '@/stores/toolsContent'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const router = useRouter()
const store = useToolsContentStore()
const auth = useAuthStore()

onMounted(() => { void store.ensure() })

const tool = computed(() => TOOLS.find(t => t.key === route.params.toolId) || null)
const content = computed(() => (tool.value ? store.of(tool.value.key) : null))

// 页签组件懒加载（每个页签只解析一次）
const tabComps = computed(() => {
  const map: Record<string, ReturnType<typeof defineAsyncComponent>> = {}
  for (const tab of tool.value?.tabs || []) {
    map[tab.key] = defineAsyncComponent(tab.comp)
  }
  return map
})
const activeTab = ref('')
watch(
  [tool, () => route.params.toolId],
  () => {
    if (!tool.value) { router.replace('/tools'); return }
    if (!tool.value.tabs.some(t => t.key === activeTab.value)) {
      activeTab.value = tool.value.tabs[0]?.key || ''
    }
  },
  { immediate: true },
)
const canManage = computed(() => auth.can('action.tools.content.manage'))

function goCta() {
  const target = content.value?.cta_target || ''
  if (target.startsWith('/')) router.push(target)
}
</script>

<template>
  <div v-if="tool && content" class="tool-page">
    <div class="crumb">
      <a @click="router.push('/portal')">首页</a>
      <span class="sep">/</span>
      <a @click="router.push('/tools')">工具</a>
      <span class="sep">/</span>
      <span class="cur">{{ content.name }}</span>
    </div>

    <div class="title-row">
      <h1>{{ content.page_title || content.name }}</h1>
      <div v-if="tool.tabs.length > 1" class="mode-toggle" role="tablist">
        <button
          v-for="tab in tool.tabs" :key="tab.key"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >{{ tab.label }}</button>
      </div>
      <p class="sub">{{ content.page_sub }}</p>
    </div>

    <div class="tab-body">
      <component :is="tabComps[activeTab]" v-if="activeTab && tabComps[activeTab]" />
    </div>

    <section v-if="content.doc_visible && content.doc_items?.length" class="doc-sec">
      <div class="doc-head">
        <h2>{{ content.doc_title }}</h2>
        <span class="doc-src">内容来自工具内容库 · 非硬编码</span>
        <button v-if="canManage" class="doc-edit" @click="router.push('/tools/admin')">✎ 去后台编辑</button>
      </div>
      <div class="fs-grid">
        <div v-for="(item, i) in content.doc_items" :key="i" class="fs-item">
          <div class="fs-name">{{ item.title }}</div>
          <div v-if="item.formula" class="fs-formula cpq-reading">{{ item.formula }}</div>
          <p>{{ item.text }}</p>
        </div>
      </div>
    </section>

    <div v-if="content.cta_visible" class="cta-strip">
      <span class="cta-text">{{ content.cta_text }}</span>
      <button class="cta-btn" @click="goCta">{{ content.cta_button }}</button>
    </div>
  </div>
</template>

<style scoped>
.tool-page { max-width: 1600px; margin: 0 auto; padding: var(--cpq-space-4) var(--cpq-space-5) 80px; }
.crumb { display: flex; align-items: center; gap: var(--cpq-space-2); margin-bottom: var(--cpq-space-4); font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.crumb a { color: var(--cpq-text-muted); cursor: pointer; }
.crumb a:hover { color: var(--cpq-accent-primary); }
.crumb .sep { color: var(--cpq-text-disabled); }
.crumb .cur { color: var(--cpq-text-secondary); }

.title-row { display: flex; align-items: center; gap: var(--cpq-space-3); flex-wrap: wrap; margin-bottom: var(--cpq-space-4); }
.title-row h1 { font-size: var(--cpq-font-size-2xl); font-weight: var(--cpq-font-weight-semibold); line-height: var(--cpq-line-height-heading); color: var(--cpq-text-primary); }
.title-row .sub { flex-basis: 100%; margin-top: var(--cpq-space-1); font-size: var(--cpq-font-size-base); color: var(--cpq-text-secondary); }

.mode-toggle { display: inline-flex; border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-md); overflow: hidden; background: var(--cpq-glass-1-bg); }
.mode-toggle button {
  border: 0; background: transparent; cursor: pointer;
  padding: var(--cpq-space-1) var(--cpq-space-4);
  font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary);
  display: inline-flex; align-items: center; gap: var(--cpq-space-1);
  transition: all var(--cpq-dur-1) var(--cpq-ease-out-expo);
}
.mode-toggle button + button { border-left: 1px solid var(--cpq-glass-border); }
.mode-toggle button.active { background: var(--cpq-accent-primary); color: var(--cpq-accent-on-primary); font-weight: var(--cpq-font-weight-semibold); }

.tab-body { min-height: 0; }

.doc-sec { margin-top: var(--cpq-space-5); }
.doc-head { display: flex; align-items: center; gap: var(--cpq-space-3); margin-bottom: var(--cpq-space-3); flex-wrap: wrap; }
.doc-head h2 { font-size: var(--cpq-font-size-xl); font-weight: var(--cpq-font-weight-semibold); color: var(--cpq-text-primary); }
.doc-src { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); padding: 1px var(--cpq-space-2); border-radius: var(--cpq-radius-full); background: var(--cpq-overlay-a5); }
.doc-edit { margin-left: auto; font-size: var(--cpq-font-size-sm); color: var(--cpq-accent-primary); cursor: pointer; background: none; border: 0; }
.doc-edit:hover { color: var(--cpq-accent-primary-light); text-decoration: underline; }
.fs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr)); gap: var(--cpq-space-4); }
.fs-item { padding: var(--cpq-space-4); border-radius: var(--cpq-radius-lg); background: var(--cpq-glass-1-bg); border: 1px solid var(--cpq-border-secondary); }
.fs-item .fs-name { font-size: var(--cpq-font-size-base); font-weight: var(--cpq-font-weight-semibold); margin-bottom: var(--cpq-space-2); color: var(--cpq-text-primary); }
.fs-item .fs-formula { font-size: var(--cpq-font-size-sm); color: var(--cpq-accent-primary); background: var(--cpq-overlay-a5); border-radius: var(--cpq-radius-sm); padding: var(--cpq-space-2) var(--cpq-space-3); margin-bottom: var(--cpq-space-2); }
.fs-item p { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); }

.cta-strip {
  margin-top: var(--cpq-space-5);
  padding: var(--cpq-space-4) var(--cpq-space-5);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-2-bg);
  border: 1px solid var(--cpq-border-secondary);
  display: flex; align-items: center; gap: var(--cpq-space-3); flex-wrap: wrap;
}
.cta-text { flex: 1; min-width: 200px; font-size: var(--cpq-font-size-base); color: var(--cpq-text-secondary); }
.cta-btn {
  border: 0; cursor: pointer; padding: var(--cpq-space-2) var(--cpq-space-4);
  border-radius: var(--cpq-radius-sm); background: var(--cpq-accent-gradient);
  color: var(--cpq-accent-on-primary); font-size: var(--cpq-font-size-sm); font-weight: var(--cpq-font-weight-semibold);
  box-shadow: 0 4px 14px var(--cpq-shadow-color-soft);
  transition: transform var(--cpq-dur-1) var(--cpq-ease-spring);
}
.cta-btn:hover { transform: translateY(-1px); }

@media (max-width: 768px) {
  .tool-page { padding: var(--cpq-space-3) var(--cpq-space-4) 80px; }
  .crumb { margin-bottom: var(--cpq-space-3); }
  .fs-grid { grid-template-columns: 1fr; }
  .cta-strip { flex-direction: column; align-items: stretch; padding: var(--cpq-space-4); }
  .cta-btn { width: 100%; }
}
</style>
