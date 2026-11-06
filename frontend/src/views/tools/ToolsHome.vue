<script setup lang="ts">
/** 工具中心（/tools）—— 顶栏一级项。分类分组的工具卡片网格，
 *  文案全部来自 toolsContent store（rules.tool_contents，后台编辑器可改）。
 *  卡片节奏与玻璃配方走 tokens；层级靠字号字重留白（无彩条无圆点）。 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { TOOL_ICONS, TOOLS } from '@/constants/toolsRegistry'
import { useToolsContentStore } from '@/stores/toolsContent'

const router = useRouter()
const store = useToolsContentStore()

onMounted(() => { void store.ensure() })

const groups = computed(() => {
  const items = TOOLS
    .map(t => ({ def: t, content: store.of(t.key) }))
    .filter(x => x.content.visible !== false)
    .sort((a, b) => (a.content.order ?? 0) - (b.content.order ?? 0))
  const byCategory = new Map<string, typeof items>()
  for (const x of items) {
    const cat = x.content.category || '更多工具'
    if (!byCategory.has(cat)) byCategory.set(cat, [])
    byCategory.get(cat)!.push(x)
  }
  return [...byCategory.entries()].map(([category, list]) => ({ category, list }))
})

function iconOf(name: string) {
  return TOOL_ICONS[name] || TOOL_ICONS.appstore
}
</script>

<template>
  <div class="tools-page">
    <div class="page-head">
      <h1>工具</h1>
    </div>

    <section v-for="g in groups" :key="g.category" class="group">
      <div class="group-head">
        <h2>{{ g.category }}</h2>
        <span class="count cpq-reading">{{ g.list.length }} 个工具</span>
      </div>
      <div class="tool-grid">
        <button
          v-for="x in g.list" :key="x.def.key"
          class="tool-card"
          @click="router.push(x.def.path)"
        >
          <span class="icon-badge">
            <component :is="iconOf(x.def.icon)" />
          </span>
          <span class="tc-name">{{ x.content.name }}</span>
          <span class="tc-desc">{{ x.content.desc }}</span>
          <span v-if="x.content.tags?.length" class="tc-meta">
            <span v-for="tag in x.content.tags" :key="tag" class="chip">{{ tag }}</span>
          </span>
          <span class="open-link">打开工具 <span class="tc-arrow">→</span></span>
        </button>
      </div>
    </section>

    <p v-if="!groups.length" class="hub-note">暂无上架工具。</p>
  </div>
</template>

<style scoped>
.tools-page { max-width: 1600px; margin: 0 auto; padding: var(--cpq-space-4) var(--cpq-space-5) 80px; }
.page-head { margin-bottom: var(--cpq-space-5); }
.page-head h1 { font-size: var(--cpq-font-size-2xl); font-weight: var(--cpq-font-weight-semibold); line-height: var(--cpq-line-height-heading); color: var(--cpq-text-primary); }

.group { margin-bottom: var(--cpq-space-6); }
.group-head { display: flex; align-items: baseline; gap: var(--cpq-space-3); margin-bottom: var(--cpq-space-4); }
.group-head h2 { font-size: var(--cpq-font-size-lg); font-weight: var(--cpq-font-weight-semibold); color: var(--cpq-text-primary); }
.group-head .count { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); padding: 0 var(--cpq-space-2); border-radius: var(--cpq-radius-sm); background: var(--cpq-overlay-a5); }

.tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); gap: var(--cpq-space-4); }
.tool-card {
  position: relative;
  padding: var(--cpq-space-4);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border: 1px solid var(--cpq-border-secondary);
  box-shadow: var(--cpq-glass-card-shadow);
  cursor: pointer;
  transition: transform var(--cpq-dur-2) var(--cpq-ease-spring), box-shadow var(--cpq-dur-2) var(--cpq-ease-out-expo), border-color var(--cpq-dur-1);
  display: flex; flex-direction: column; gap: var(--cpq-space-3);
  text-align: left; font: inherit; color: inherit;
}
.tool-card:hover { transform: translateY(-2px); box-shadow: var(--cpq-glass-card-shadow-hover); border-color: var(--cpq-border-light); }
.icon-badge {
  width: 36px; height: 36px; flex: none;
  border-radius: var(--cpq-radius-md);
  display: grid; place-items: center;
  background: var(--cpq-notif-violet-bg); color: var(--cpq-notif-violet);
  font-size: var(--cpq-font-size-lg);
}
.tc-name { font-size: var(--cpq-font-size-lg); font-weight: var(--cpq-font-weight-semibold); color: var(--cpq-text-primary); }
.tc-desc { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); flex: 1; }
.tc-meta { display: flex; align-items: center; gap: var(--cpq-space-2); flex-wrap: wrap; }
.chip { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); padding: 1px var(--cpq-space-2); border-radius: var(--cpq-radius-full); background: var(--cpq-overlay-a5); }
.open-link { margin-top: var(--cpq-space-1); font-size: var(--cpq-font-size-sm); font-weight: var(--cpq-font-weight-semibold); color: var(--cpq-accent-primary); }
.tool-card:hover .open-link { color: var(--cpq-accent-primary-light); }
.tc-arrow { transition: transform var(--cpq-dur-1) var(--cpq-ease-out-expo); display: inline-block; }
.tool-card:hover .tc-arrow { transform: translateX(3px); }
.hub-note { margin-top: var(--cpq-space-5); font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }

@media (max-width: 768px) {
  .tools-page { padding: var(--cpq-space-4); }
}
</style>
