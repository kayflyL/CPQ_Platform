<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import SchemeEditor from '@/components/opportunity/SchemeEditor.vue'
import ArtifactCard from '@/components/assistant/ArtifactCard.vue'
import { useNodeArtifact } from '@/composables/useNodeArtifact'
import MarkdownContent from '@/views/admin/strategy/MarkdownContent.vue'
import RequirementForm from '@/components/flow/RequirementForm.vue'
import { shapeOf } from './artifactShapes'

const { artifact, close } = useNodeArtifact()
const props = defineProps<{ bomScheme?: any }>()

// 产物卡类：ArtifactCard 自带 z-2000 弹窗直接承载（此前嵌在本弹窗里=双层弹窗，
// 外层只剩一个空标题壳，2026-10-22 用户实测）。本弹窗只承载其余产物类型。
const isCard = computed(() => artifact.value?.kind === 'artifact_card')
// 换产物时强制重建：卡片内部按 refs 懒加载且不重置，同一实例换卡不会重拉数据
const cardKey = computed(() =>
  JSON.stringify(artifact.value?.data?.card?.refs || {}) + '|' + (artifact.value?.data?.card?.title || ''))
const open = computed({
  get: () => !!artifact.value && !isCard.value,
  set: (v: boolean) => { if (!v) close() },
})

const reqRef = ref<{ fromSlots: (slots: Record<string, any>) => void } | null>(null)
const requirementText = ref('')
const bomSchemeConfigs = computed(() => Array.isArray(props.bomScheme?.configs) ? props.bomScheme.configs : [])

function normalizeRequirementSlots(data: any) {
  const d = data && typeof data === 'object' ? data : {}
  return {
    ...d,
    server_type: d.server_type_name || d.server_type || '',
    platform_type: d.series || d.platform_type || '',
    chassis_form: d.form || d.chassis_form || '',
  }
}

watch([artifact, reqRef], async ([a]) => {
  requirementText.value = (a?.data && typeof a.data === 'object' && a.data.requirement_text)
    || (a?.input && typeof a.input === 'object' && a.input.requirement_text)
    || (a?.output && typeof a.output === 'object' && a.output.requirement_text)
    || ''
  if (a?.kind === 'requirement_slots') {
    await nextTick()
    reqRef.value?.fromSlots(normalizeRequirementSlots(a.data || {}))
  }
}, { immediate: true })

const artifactData = computed(() => artifact.value?.data)
const kind = computed(() => artifact.value?.kind || '')
// ── 形状分派（P2 产物契约域化·前端半）：kind → shape 见 artifactShapes.ts。
// 新域产物 = 后端 builder 产出形状契约 + 登记映射，本组件零改。──
const shape = computed(() => shapeOf(kind.value))
// document：markdown 优先，纯文本（requirement_text 的 data.text）兜底
const docContent = computed(() => {
  const d = artifactData.value || {}
  const md = typeof d.markdown === 'string' && d.markdown.trim() ? d.markdown : ''
  if (md) return md
  return typeof d.text === 'string' && d.text.trim() ? d.text : ''
})
// table：通用表格（rows/columns 由产物自带），列缺省按 kind 回退，行按 waived/unmatched 染色
const tableRows = computed(() => Array.isArray(artifactData.value?.rows) ? artifactData.value.rows : [])
const tableCols = computed(() => {
  const cols = Array.isArray(artifactData.value?.columns) ? artifactData.value.columns : []
  const ant = cols.map((c: any) => ({ title: c.label || c.key, dataIndex: c.key, key: c.key }))
  if (ant.length) return ant
  if (kind.value === 'kp_table') return kpCols
  return [
    { title: '配置件', dataIndex: 'catalogue', key: 'catalogue' },
    { title: '说明', dataIndex: 'description', key: 'description' },
    { title: '数量', dataIndex: 'qty', key: 'qty', width: 64 },
  ]
})
const rowClass = (record: any) => (record.waived ? 'kp-row-waived' : (record.unmatched ? 'kp-row-unmatched' : ''))
// kind 特有的提示行（表头上方的结构化事实）：l6=锁定机型/理由；kp=落地统计/豁免行
const tableHints = computed(() => {
  const d = artifactData.value || {}
  if (kind.value === 'kp_table') {
    const hints: string[] = []
    const s = d.summary
    if (s) hints.push(`KP 落地 ${s.kp_count ?? 0} 项，未命中 ${s.unmatched_count ?? 0} 项，规格偏差 ${s.spec_mismatch_count ?? 0} 项`)
    const w = Array.isArray(d.unmatched) ? [] : (kpRows.value.filter((r: any) => r.waived))
    if (w.length) hints.push(`其中 ${w.length} 行库内无料（客户已知悉、按原需求留白）：${w.map((r: any) => r.catalogue).join('、')}`)
    return hints
  }
  const hints: string[] = []
  if (d.chosen) hints.push(`锁定机型：${d.chosen}`)
  if (d.reason) hints.push(`推荐理由：${d.reason}`)
  if (d.note) hints.push(String(d.note))
  return hints
})
const kpRows = computed(() => Array.isArray(artifactData.value?.rows) ? artifactData.value.rows : [])
const unmatchedRows = computed(() => Array.isArray(artifactData.value?.unmatched) ? artifactData.value.unmatched : [])
const kpCols = [
  { title: 'Catalogue', dataIndex: 'part_category', key: 'part_category', width: 120 },
  { title: 'Configuration Description', dataIndex: 'catalogue', key: 'catalogue' },
  { title: 'Quantity', dataIndex: 'qty', key: 'qty', width: 90 },
]
</script>

<template>
  <!-- 产物卡类：顶层直挂 ArtifactCard（自带弹窗承载），本组件的 a-modal 只管其余产物 -->
  <ArtifactCard v-if="isCard" :key="cardKey" :card="artifact?.data?.card" auto-open />

  <a-modal
    v-else
    v-model:open="open"
    :title="artifact?.title || '节点产出物'"
    :footer="null"
    width="min(1180px, calc(100vw - 24px))"
    :z-index="1800"
    :body-style="{ padding: '14px', maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', overflowX: 'hidden' }"
  >
    <!-- scheme：BOM 方案（props 注入实体，未生成时提示重跑） -->
    <template v-if="artifact?.kind === 'bom_scheme'">
      <div v-if="bomScheme" class="artifact-scheme">
        <SchemeEditor :configs="bomSchemeConfigs" readonly :show-toolbar="false" />
      </div>
      <div v-else class="artifact-empty">BOM 方案尚未生成完整实体，请重新试运行。</div>
    </template>

    <!-- form：线索登记表 -->
    <template v-else-if="artifact?.kind === 'requirement_slots'">
      <RequirementForm v-if="artifact" ref="reqRef" v-model:req-text="requirementText" readonly />
    </template>

    <!-- 待补充字段 -->
    <template v-else-if="artifact?.kind === 'requirement_missing'">
      <div class="missing-title">待补充字段</div>
      <a-tag v-for="(f, i) in artifactData?.missing_fields || []" :key="i" style="margin-right:8px">{{ f }}</a-tag>
    </template>

    <!-- document：markdown / 纯文本（requirement_text、data_report、document…） -->
    <template v-else-if="shape === 'document'">
      <div v-if="docContent" class="artifact-doc">
        <MarkdownContent :source="docContent" />
      </div>
      <div v-else class="artifact-empty">本节点尚未产出报告内容。</div>
    </template>

    <!-- table：通用表格（rows/columns 产物自带；kind 特有提示行保留） -->
    <template v-else-if="shape === 'table'">
      <div v-for="(h, i) in tableHints" :key="i" class="artifact-hint">{{ h }}</div>
      <a-table v-if="tableRows.length" :data-source="tableRows" :columns="tableCols" size="small" :row-key="(_: any, i: number) => i" :pagination="false" :row-class-name="rowClass" />
      <div v-if="kind === 'kp_table' && unmatchedRows.length" class="artifact-unmatched">
        <div class="artifact-unmatched-title">未匹配 / 待确认（未能从配件库锁定真实料号，不作 KP 配置表行）</div>
        <ul class="artifact-unmatched-list">
          <li v-for="(u, i) in unmatchedRows" :key="i">
            <span class="artifact-unmatched-cat">{{ u.category || '未分类' }}</span>
            <span v-if="u.description" class="artifact-unmatched-desc">（{{ u.description }}）</span>
            <span class="artifact-unmatched-qty">× {{ u.qty ?? 1 }}</span>
          </li>
        </ul>
      </div>
      <div v-if="!tableRows.length" class="artifact-empty">暂无数据。</div>
    </template>

    <!-- raw：plans/parts_proposal/未登记 kind 原样 JSON（白盒不装懂） -->
    <template v-else-if="artifact?.kind === 'plans'">
      <div class="plans-count">共 {{ artifactData?.plans_count ?? 0 }} 个方案</div>
      <pre class="artifact-raw">{{ JSON.stringify(artifactData, null, 2) }}</pre>
    </template>

    <template v-else>
      <pre class="artifact-raw">{{ JSON.stringify(artifactData, null, 2) }}</pre>
    </template>
  </a-modal>
</template>

<style scoped>
.artifact-empty { color: var(--cpq-text-muted); font-size: 13px; padding: 12px 0; }
.artifact-doc { max-height: calc(100vh - 240px); overflow-y: auto; padding: 4px 8px; }
.artifact-scheme { min-height: 220px; }
.artifact-raw { white-space: pre-wrap; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); }
.missing-title { font-weight: 600; margin-bottom: 8px; }
.plans-count { font-weight: 600; margin-bottom: 8px; }
.artifact-hint { font-weight: 600; margin-bottom: 8px; color: var(--cpq-text-secondary); }
:deep(.kp-row-waived td) { color: var(--cpq-text-warning, #d48806); }
:deep(.kp-row-unmatched td) { color: var(--cpq-text-muted); font-style: italic; }
.artifact-unmatched { margin-top: 10px; padding: 8px 12px; border: 1px dashed var(--cpq-border-color, #d9d9d9); border-radius: var(--cpq-radius-sm); background: var(--cpq-bg-secondary, #fafafa); }
.artifact-unmatched-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; color: var(--cpq-text-warning, #d48806); }
.artifact-unmatched-list { margin: 0; padding: 0 0 0 16px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); line-height: 20px; }
.artifact-unmatched-cat { font-weight: 600; }
.artifact-unmatched-desc { color: var(--cpq-text-muted); }
.artifact-unmatched-qty { margin-left: 6px; color: var(--cpq-text-muted); }
</style>
