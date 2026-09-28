<template>
  <a-popover v-model:open="open" trigger="click" placement="bottomRight" overlay-class-name="part-filter-pop">
    <button class="pf-trigger" :class="{ active: applied.length > 0 }" title="按报价单配件筛选商机">
      <FilterOutlined />
      配件筛选
      <span v-if="applied.length" class="pf-dot"></span>
    </button>
    <template #content>
      <div class="pf-panel">
        <div class="pf-title">按报价单配件筛选</div>
        <div class="pf-hint">多行条件 = <b>同时满足</b>（同一张报价里都含）；同行多关键词 = <b>任一命中</b>；关键词按<b>包含</b>匹配——敲 5090 回车即命中所有写法，无需逐个挑选候选。</div>

        <div v-for="(row, i) in draft" :key="i" class="pf-row">
          <span class="pf-and" :class="{ ghost: i === 0 }">且</span>
          <a-select
            v-model:value="row.category"
            size="small"
            style="width: 100px; flex: none"
            :options="categoryOptions"
            @change="row.options = []"
          />
          <div class="pf-kw">
            <span v-for="(kw, j) in row.keywords" :key="kw + j" class="pf-tag">
              {{ kw }}<i @click="row.keywords.splice(j, 1)">✕</i>
            </span>
            <a-auto-complete
              v-model:value="row.draftKw"
              :options="row.options"
              :default-active-first-option="false"
              size="small"
              style="flex: 1; min-width: 96px"
              placeholder="如：5090，回车直接添加"
              @select="(v: any) => addKeyword(row, String(v))"
              @keydown.enter.prevent="commitDraft(row)"
              @blur="commitDraft(row)"
            />
          </div>
          <span class="pf-qty" :class="{ empty: !row.qtyMin }">
            <label>≥</label>
            <a-input-number v-model:value="row.qtyMin" :min="1" :max="999" :controls="false" size="small" style="width: 52px" placeholder="—" />
          </span>
          <button class="pf-del" title="删除此行" @click="draft.splice(i, 1)">✕</button>
        </div>

        <button class="pf-add" @click="draft.push(newRow())">＋ 添加条件</button>

        <div class="pf-foot">
          <span class="pf-note">应用后，周期筛选按<b>报价创建时间</b>过滤；命中结果显示在列表「命中配件」列。</span>
          <button class="pf-btn" @click="clearAll">清空</button>
          <button class="pf-btn primary" @click="apply">应用</button>
        </div>
      </div>
    </template>
  </a-popover>
</template>

<script setup lang="ts">
/**
 * 配件筛选（商机列表）：条件行 = 类别 + 型号关键词（多个=任一） + 可选数量≥N，多行=同时满足。
 * 型号建议来自 /api/opportunities/part-suggest（报价明细真实出现过的 catalogue，按使用次数）。
 * 应用态（chips 回显 / 参数拼装 / 命中列）由父页面持有，本组件只管编辑弹层。
 */
import { ref, watch } from 'vue'
import axios from 'axios'
import { FilterOutlined } from '@ant-design/icons-vue'

export type PartFilterRow = { category: string; keywords: string[]; qtyMin: number | null }

const props = defineProps<{ applied: PartFilterRow[] }>()
const emit = defineEmits<{
  (e: 'apply', rows: PartFilterRow[]): void
  (e: 'clear'): void
}>()

const open = ref(false)
type DraftRow = PartFilterRow & { draftKw: string; options: { value: string; label: string }[] }
const draft = ref<DraftRow[]>([])
const categoryOptions = ref<{ value: string; label: string }[]>([{ value: '', label: '全部类别' }])
let categoriesLoaded = false

function newRow(category = ''): DraftRow {
  return { category, keywords: [], qtyMin: null, draftKw: '', options: [] }
}

// 打开时从应用态克隆编辑稿；首次打开顺带拉类别清单
watch(open, (v) => {
  if (!v) return
  draft.value = props.applied.length
    ? props.applied.map((r) => ({ ...r, keywords: [...r.keywords], draftKw: '', options: [] }))
    : [newRow()]
  if (!categoriesLoaded) {
    categoriesLoaded = true
    axios.get('/api/opportunities/part-categories').then((res) => {
      const items = (res.data?.items || []) as { value: string; count: number }[]
      categoryOptions.value = [
        { value: '', label: '全部类别' },
        ...items.map((i) => ({ value: i.value, label: `${i.value} (${i.count})` })),
      ]
    }).catch(() => { categoriesLoaded = false })
  }
})

function addKeyword(row: DraftRow, kw: string) {
  const k = kw.trim()
  row.draftKw = ''
  if (!k || row.keywords.includes(k) || row.keywords.length >= 6) return
  row.keywords.push(k)
}
// default-active-first-option=false 是关键：下拉展开时回车不会被 antd 抢去选中第一条候选，
// 敲 5090 回车 = 原文 "5090" 入词，后端按包含匹配即命中所有写法；鼠标点候选仍精确入选。
function commitDraft(row: DraftRow) {
  if (row.draftKw.trim()) addKeyword(row, row.draftKw)
}

// 型号建议：输入停顿 250ms 拉一次（带类别限定）
let suggestTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => draft.value.map((r) => r.draftKw).join(''),
  () => {
    if (suggestTimer) clearTimeout(suggestTimer)
    suggestTimer = setTimeout(() => {
      for (const row of draft.value) {
        const kw = row.draftKw.trim()
        if (!kw) { row.options = []; continue }
        axios.get('/api/opportunities/part-suggest', {
          params: { category: row.category || undefined, q: kw },
        }).then((res) => {
          const items = (res.data?.items || []) as { value: string; count: number }[]
          row.options = items.map((i) => ({ value: i.value, label: `${i.value}（${i.count}）` }))
        }).catch(() => { row.options = [] })
      }
    }, 250)
  }
)

function apply() {
  const rows = draft.value
    .filter((r) => r.keywords.length > 0)
    .map((r) => ({ category: r.category || '', keywords: [...r.keywords], qtyMin: r.qtyMin ?? null }))
  emit('apply', rows)
  open.value = false
}
function clearAll() {
  draft.value = [newRow()]
  emit('clear')
  open.value = false
}
</script>

<style scoped>
.pf-trigger {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: var(--cpq-radius-sm, 8px);
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  background: var(--cpq-glass-2-bg, rgba(255, 255, 255, 0.72));
  color: var(--cpq-text-secondary); font-size: 12px; font-family: inherit; cursor: pointer;
  transition: all 0.15s ease; white-space: nowrap;
}
.pf-trigger:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-text-primary); }
.pf-trigger.active {
  background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: #fff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.3);
}
.pf-dot { width: 6px; height: 6px; border-radius: 50%; background: #fff; }
.pf-panel { width: 480px; max-width: calc(100vw - 48px); }
.pf-title { font-size: 13px; font-weight: 700; color: var(--cpq-text-primary); }
.pf-hint { font-size: 11px; color: var(--cpq-text-secondary); margin: 5px 0 10px; line-height: 1.6; }
.pf-hint b { color: var(--cpq-text-primary); }
.pf-row { display: flex; align-items: center; gap: 7px; margin-bottom: 8px; }
.pf-and { width: 26px; flex: none; text-align: center; font-size: 10px; color: var(--cpq-text-muted); }
.pf-and.ghost { visibility: hidden; }
.pf-kw {
  flex: 1; display: flex; flex-wrap: wrap; align-items: center; gap: 4px; min-height: 28px;
  border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  border-radius: var(--cpq-radius-sm, 8px); padding: 2px 6px; background: var(--cpq-glass-2-bg, rgba(255, 255, 255, 0.85));
}
.pf-tag {
  display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--cpq-text-primary);
  background: rgba(22, 119, 255, 0.08); border: 1px solid rgba(22, 119, 255, 0.25);
  border-radius: 6px; padding: 0 4px 0 7px;
}
.pf-tag i { font-style: normal; font-size: 10px; color: var(--cpq-text-muted); cursor: pointer; }
.pf-tag i:hover { color: var(--cpq-accent-danger); }
.pf-qty { display: inline-flex; align-items: center; gap: 3px; flex: none; }
.pf-qty label { font-size: 11px; color: var(--cpq-text-secondary); }
.pf-qty.empty { opacity: 0.45; }
.pf-del {
  border: 0; background: transparent; color: var(--cpq-text-muted); cursor: pointer;
  font-size: 12px; padding: 2px 4px; border-radius: 6px; flex: none;
}
.pf-del:hover { color: var(--cpq-accent-danger); background: rgba(255, 107, 107, 0.1); }
.pf-add {
  border: 0; background: transparent; color: var(--cpq-accent-primary); font-size: 12px;
  font-family: inherit; cursor: pointer; padding: 2px 4px;
}
.pf-add:hover { text-decoration: underline; }
.pf-foot {
  display: flex; align-items: center; gap: 8px; margin-top: 10px; padding-top: 10px;
  border-top: 1px dashed var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
}
.pf-note { flex: 1; font-size: 11px; color: var(--cpq-text-muted); line-height: 1.5; }
.pf-note b { color: var(--cpq-text-secondary); }
.pf-btn {
  font-family: inherit; font-size: 12px; border-radius: var(--cpq-radius-sm, 8px); padding: 4px 14px;
  cursor: pointer; border: 1px solid var(--cpq-glass-border, rgba(120, 144, 176, 0.38));
  background: transparent; color: var(--cpq-text-secondary); transition: all 0.15s ease; flex: none;
}
.pf-btn:hover { color: var(--cpq-text-primary); }
.pf-btn.primary { background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); color: #fff; }
.pf-btn.primary:hover { background: #3c8dff; }
@media (max-width: 768px) {
  .pf-panel { width: min(420px, calc(100vw - 40px)); }
  .pf-note { display: none; }
}
</style>
