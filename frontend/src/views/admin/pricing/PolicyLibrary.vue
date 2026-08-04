<script setup lang="ts">
/** 策略文档库 body —— 左分类目录(计数) + 右文档卡片网格。
 *  点卡片 emit open-doc(阅读交给 DocReaderOverlay);新建/编辑(PolicyDocEditor)/删除在本组件内。
 *  卡片统一白玻璃(镜像 ServerModelCard),分类不带配色(Glass Console:色彩只给语义态)。 */
import { ref, computed, onMounted } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { policyDocApi, type PolicyDoc } from '@/api/strategies'
import { readDocBody, DOC_CATEGORIES, type StrategyModule } from '@/constants/policyMeta'
import PolicyDocEditor from './PolicyDocEditor.vue'

const props = defineProps<{ module: StrategyModule }>()
const emit = defineEmits<{ 'open-doc': [doc: PolicyDoc] }>()

const docs = ref<PolicyDoc[]>([])
/** 本模块文档（按 body.module 过滤；存量无 module 归 'pricing'，见 readDocBody）*/
const moduleDocs = computed(() => docs.value.filter(d => readDocBody(d.body).module === props.module))
const loading = ref(false)
const filterCat = ref<string>('all')
const search = ref('')
const editorOpen = ref(false)
const editing = ref<PolicyDoc | null>(null)

const cats = computed(() => {
  const present = new Set(moduleDocs.value.map((d) => readDocBody(d.body).category))
  return [
    { value: 'all', label: '全部', count: moduleDocs.value.length },
    ...DOC_CATEGORIES.filter((c) => present.has(c.value)).map((c) => ({
      value: c.value,
      label: c.label,
      count: moduleDocs.value.filter((d) => readDocBody(d.body).category === c.value).length,
    })),
  ]
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  let list = filterCat.value === 'all' ? moduleDocs.value : moduleDocs.value.filter((d) => readDocBody(d.body).category === filterCat.value)
  if (q) list = list.filter((d) => (d.name + (d.description || '')).toLowerCase().includes(q))
  return [...list].sort((a, b) => {
    const ba = readDocBody(a.body), bb = readDocBody(b.body)
    return ba.sort_order - bb.sort_order || (a.created_at || '').localeCompare(b.created_at || '')
  })
})

async function load() {
  loading.value = true
  try {
    const res = await policyDocApi.list(props.module)
    docs.value = res.docs || []
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载文档失败')
  } finally {
    loading.value = false
  }
}

function openNew() { editing.value = null; editorOpen.value = true }
function openEdit(d: PolicyDoc, e: Event) { e.stopPropagation(); editing.value = d; editorOpen.value = true }
async function onSaved() { editorOpen.value = false; await load() }

function remove(d: PolicyDoc, e: Event) {
  e.stopPropagation()
  Modal.confirm({
    title: '删除该文档？',
    content: `「${d.name}」将被删除,不可恢复。`,
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      try { await policyDocApi.remove(props.module, d.created_at || ''); message.success('已删除'); await load() }
      catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

function excerpt(d: PolicyDoc): string {
  const b = readDocBody(d.body)
  const firstLine = b.content_markdown.split('\n').find((l) => l.trim() && !l.startsWith('#'))
  return d.description || (firstLine || '').replace(/[`*|#]/g, '').slice(0, 60) || '—'
}
function fmtDate(s: string | null) { return s ? s.replace('T', ' ').slice(0, 10) : '—' }

onMounted(load)
</script>

<template>
  <div class="policy-lib">
    <!-- 左:分类目录 -->
    <aside class="pl-cats">
      <div class="pl-cats-title">
        <span>文档库</span><em>共 {{ moduleDocs.length }}</em>
      </div>
      <div class="pl-cat-list">
        <div
          v-for="c in cats"
          :key="c.value"
          class="pl-cat-row"
          :class="{ active: filterCat === c.value }"
          @click="filterCat = c.value"
        >
          <span class="pl-cat-label">{{ c.label }}</span>
          <span class="pl-cat-count">{{ c.count }}</span>
        </div>
      </div>
    </aside>

    <!-- 右:卡片网格 -->
    <section class="pl-main">
      <div class="pl-toolbar">
        <a-input v-model:value="search" placeholder="搜索文档..." allow-clear class="pl-search" />
        <a-button type="primary" @click="openNew">+ 新建文档</a-button>
      </div>

      <a-spin :spinning="loading">
        <div v-if="filtered.length" class="pl-grid">
          <div
            v-for="d in filtered"
            :key="d.created_at || d.name"
            class="pl-card is-clickable"
            @click="emit('open-doc', d)"
          >
            <div class="pl-card-top">
              <span class="pl-card-cat">{{ readDocBody(d.body).category }}</span>
              <span v-if="d.status !== 'active'" class="pl-card-status" :data-status="d.status">{{ d.status }}</span>
            </div>
            <div class="pl-card-title">{{ d.name }}</div>
            <div class="pl-card-excerpt">{{ excerpt(d) }}</div>
            <div class="pl-card-foot">
              <span class="pl-card-meta">v{{ d.version }} · {{ fmtDate(d.updated_at) }}</span>
              <span class="pl-card-actions">
                <button class="pl-act" @click="openEdit(d, $event)">编辑</button>
                <button class="pl-act pl-act-danger" @click="remove(d, $event)">删除</button>
              </span>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无文档,点「新建文档」添加" style="padding: 60px 0" />
      </a-spin>
    </section>

    <PolicyDocEditor v-model:open="editorOpen" :module="module" :doc="editing" @saved="onSaved" />
  </div>
</template>

<style scoped>
.policy-lib { display: flex; gap: 16px; align-items: flex-start; }

/* 左:分类目录(白玻璃面板) */
.pl-cats {
  flex: 0 0 200px;
  border-radius: 14px;
  border: 1px solid var(--cpq-glass-border);
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 60%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 10px 30px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
  padding: 12px 10px;
  position: sticky;
  top: 76px;
}
.pl-cats-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 2px 8px 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-muted);
  letter-spacing: 0.06em;
}
.pl-cats-title em { font-style: normal; font-weight: 400; color: var(--cpq-text-disabled); }
.pl-cat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  font-size: 13.5px;
  color: var(--cpq-text-secondary);
}
.pl-cat-row:hover { background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); }
.pl-cat-row.active { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary); font-weight: 600; }
.pl-cat-label { flex: 1; }
.pl-cat-count { font-size: 11px; color: var(--cpq-text-muted); }
.pl-cat-row.active .pl-cat-count { color: var(--cpq-accent-primary); }

/* 右:主区 */
.pl-main { flex: 1 1 auto; min-width: 0; }
.pl-toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
.pl-search { max-width: 280px; }
.pl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 14px;
}

/* 文档卡:镜像 ServerModelCard 白玻璃配方(与门户/服务器卡统一) */
.pl-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px 12px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 10px 30px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  min-height: 132px;
}
.pl-card.is-clickable { cursor: pointer; }
.pl-card.is-clickable:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-2px);
  box-shadow: 0 16px 40px var(--cpq-shadow-color-strong), inset 0 1px 0 var(--cpq-overlay-w15);
}
.pl-card-top { display: flex; align-items: center; justify-content: space-between; }
.pl-card-cat {
  font-size: 11px;
  font-weight: 600;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6);
  padding: 2px 8px;
  border-radius: 8px;
}
.pl-card-status { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: var(--cpq-overlay-w6); color: var(--cpq-text-muted); }
.pl-card-status[data-status='archived'] { text-decoration: line-through; }
.pl-card-title {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.pl-card-excerpt {
  font-size: 12.5px;
  color: var(--cpq-text-muted);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  flex: 1;
}
.pl-card-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
}
.pl-card-meta { font-size: 11px; color: var(--cpq-text-muted); }
.pl-card-actions { margin-left: auto; display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s; }
.pl-card:hover .pl-card-actions { opacity: 1; }
.pl-act {
  border: none;
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-secondary);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}
.pl-act:hover { background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary); }
.pl-act-danger:hover { color: var(--cpq-color-danger, #ff6b6b); }
</style>
