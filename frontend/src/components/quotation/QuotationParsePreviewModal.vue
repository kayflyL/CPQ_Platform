<template>
  <a-modal
    :open="open"
    title="解析预览 — 核对并修正后生成成本表"
    width="94%"
    :footer="null"
    :destroy-on-close="true"
    :body-style="{ padding: '14px', height: '84vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }"
    @cancel="emit('cancel')"
  >
    <!-- 模板信息条：用哪套规则由「设置→解析模板」的使用位置绑定决定，弹窗不选 -->
    <div class="match-bar">
      <span class="match-text">解析模板</span>
      <a-tag color="blue">{{ resolvedTemplateName }}</a-tag>
      <span v-if="parseCameBackEmpty" class="match-warn">
        当前模板没解析出任何数据——多半是绑定错了模板，到 设置 → 解析模板 里换绑
      </span>
      <span v-else class="match-reason">在 设置 → 解析模板 中配置「成本核算 · 上传解析」用哪套规则</span>
    </div>

    <!-- 补丁 chips -->
    <div v-if="patchChips.length" class="patch-strip">
      <span class="patch-strip-label">本次修正</span>
      <a-tag
        v-for="chip in patchChips"
        :key="chip.id"
        class="patch-chip"
        closable
        @close.prevent="undoChip(chip.id)"
      >{{ chip.label }}</a-tag>
      <a class="patch-clear" @click="clearChips">全部撤销</a>
    </div>

    <!-- 主体：左=修正工具（格子档案+字段映射） / 中=网格 / 右=解析结果 -->
    <div class="preview-layout">
      <div class="preview-aside">
        <!-- 格子档案：点格看出处 -->
        <a-card v-if="dossierInfo" size="small" title="格子档案" class="side-card">
          <template #extra>
            <a-button size="small" type="text" @click="dossier = null">关闭</a-button>
          </template>
          <div class="dossier-text">{{ dossierInfo.text || '（空格）' }}</div>
          <div class="dossier-pos">第 {{ dossierInfo.row + 1 }} 行 · {{ dossierInfo.letter }} 列</div>
          <div v-if="dossierInfo.mark" class="dossier-row">
            <span class="dossier-k">角色</span>
            <a-tag size="small" :color="dossierInfo.mark.type === 'keyword' ? 'gold' : dossierInfo.mark.type === 'extracted' ? 'green' : 'blue'">
              {{ markRole(dossierInfo.mark) }}
            </a-tag>
          </div>
          <div v-if="dossierInfo.sourcedBy.length" class="dossier-row">
            <span class="dossier-k">被谁取值</span>
            <div class="dossier-sourced">
              <div v-for="s in dossierInfo.sourcedBy" :key="s.key">{{ s.label }} = {{ s.value }}</div>
            </div>
          </div>
          <div class="dossier-actions">
            <a-button
              v-if="dossierRegion"
              size="small"
              danger
              @click="skipRows([dossierInfo.row])"
            >跳过此行</a-button>
            <a-dropdown v-if="regionColumnFields(dossierRegion?.regionKey).length">
              <a-button size="small">此列绑定到…</a-button>
              <template #overlay>
                <a-menu @click="({ key }: any) => bindColumn(dossierInfo!.letter, String(key))">
                  <a-menu-item
                    v-for="f in regionColumnFields(dossierRegion?.regionKey)"
                    :key="f.field_key"
                  >{{ fieldLabels[f.field_key] || f.field_key }}</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>
        </a-card>

        <!-- 字段映射卡：列绑定驱动 -->
        <a-card size="small" title="字段映射（列绑定）" class="side-card mapping-card">
          <div v-for="group in mappingGroups" :key="group.regionId" class="mapping-group">
            <div class="mapping-region">{{ group.regionName }}</div>
            <div
              v-for="f in group.fields"
              :key="f.id"
              class="mapping-row"
              :class="{ conflict: conflicts.has(f.field_key) }"
            >
              <span class="mapping-field">{{ fieldLabels[f.field_key] || f.field_key }}</span>
              <span class="mapping-letter" :class="{ bound: (engineOverrides.col_binds || {})[f.field_key] }">
                {{ effectiveLetter(f) }}
              </span>
              <a-tooltip v-if="conflicts.has(f.field_key)" title="同区域两个字段绑到了同一列">
                <span class="mapping-warn">⚠</span>
              </a-tooltip>
              <a-button
                size="small"
                type="link"
                :class="{ picking: pickField === f.field_key }"
                @click="togglePick(f.field_key)"
              >{{ pickField === f.field_key ? '选列中…' : '点选' }}</a-button>
            </div>
          </div>
          <a-empty v-if="!mappingGroups.length" description="当前模板没有列提取字段" :image-style="{ height: '40px' }" />
        </a-card>
      </div>

      <div class="preview-main">
        <a-card size="small" :loading="parsing" class="grid-card" :body-style="{ padding: '8px', display: 'flex', flexDirection: 'column', overflow: 'hidden' }">
          <a-tabs
            v-if="sheetNames.length > 1"
            v-model:activeKey="activeSheetName"
            size="small"
            @change="handleSheetChange"
          >
            <a-tab-pane v-for="name in sheetNames" :key="name" :tab="name" />
          </a-tabs>
          <div class="grid-wrap">
            <ParseInteractiveGrid
              :previewData="previewData"
              :selectedRows="selectedRows"
              :skippedRows="skippedRows"
              :pickMode="!!pickField"
              :pickField="pickField"
              :colBinds="engineOverrides.col_binds || {}"
              :fieldLabels="fieldLabels"
              :activeCell="dossier"
              @toggle-row="onToggleRow"
              @cell-click="onCellClick"
              @pick-column="onPickColumn"
              @pick-cancel="pickField = null"
            />
            <!-- 行选浮动工具条 -->
            <div v-if="selectedRows.length" class="sel-toolbar">
              <span class="sel-count">已选 {{ selectedRows.length }} 行</span>
              <a-button size="small" danger @click="applySkipSelected">跳过所选行</a-button>
              <a-button size="small" :disabled="!cutRegion" @click="applyCutSelected">
                收口到此行{{ cutRegion ? `（${cutRegion.regionName}）` : '' }}
              </a-button>
              <a-button size="small" type="text" @click="selectedRows = []">取消</a-button>
            </div>
          </div>
        </a-card>
      </div>

      <div class="preview-side">
        <!-- 解析结果：与设置页右栏同一套共享组件 -->
        <a-card size="small" title="解析结果" class="side-card">
          <ParseResultPanel :parseResult="parseResult" />
        </a-card>
      </div>
    </div>

    <!-- 底部落点：确认生成（修正仅对本文件生效，规则维护在设置页） -->
    <div class="preview-footer">
      <span class="footer-hint">修正只对本文件本次生成生效；要改一类文件的解析规则，到 设置 → 解析模板 调整。</span>
      <a-button @click="emit('cancel')">取消</a-button>
      <a-button type="primary" :loading="confirming" :disabled="confirming" @click="onConfirm">
        确认生成成本表
      </a-button>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import ParseInteractiveGrid from '@/components/excel-parser/ParseInteractiveGrid.vue'
import ParseResultPanel from '@/components/excel-parser/ParseResultPanel.vue'
import { useExcelParser } from '@/composables/useExcelParser'

interface PatchChip {
  id: number
  kind: 'skip' | 'bind' | 'end'
  rows?: number[]
  field?: string
  letter?: string
  anchor?: string | null
  region?: string
  regionName?: string
  row?: number
  label: string
}

const props = defineProps<{
  open: boolean
  file: File | null
  opportunityId: string
  confirming: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm', payload: { parseOverrides: Record<string, any> }): void
  (e: 'cancel'): void
}>()

const {
  parseTemplates, parseRegions, parseFieldRules, businessFields,
  previewData, parseResult, parsing, sheetNames, activeSheetName, matchInfo,
  loadTemplates, loadRules, loadBusinessFields,
  handleFileUpload, refreshPreview
} = useExcelParser()

// ── 模板归属：使用位置绑定（设置页配置），弹窗只读显示后端裁决结果 ──
const UPLOAD_SCOPE = 'cost_sheet_upload'
// 旧版「记住上次选择」的遗留键，顺手清掉
const LEGACY_TPL_MEMO_KEY = 'cpq_cost_parse_template_id'

const resolvedTemplateId = computed<number | null>(() => matchInfo.value?.template_id ?? null)

const resolvedTemplateName = computed(() => {
  const t = parseTemplates.value.find(x => x.id === resolvedTemplateId.value)
  return t ? `${t.name}${t.is_fallback ? '（通用）' : ''}` : '通用'
})

// 解析全空提醒：绑定错模板时区域一个都找不到。不自动换绑——配置权在设置页。
const parseCameBackEmpty = computed(() => {
  if (!parseResult.value || parsing.value) return false
  const dr = parseResult.value.dynamic_regions || {}
  const keys = Object.keys(dr)
  if (!keys.length) return true
  return keys.every(k => !Array.isArray(dr[k]) || dr[k].length === 0)
})

// ── 补丁 chips（可撤销） ──
const patchChips = ref<PatchChip[]>([])
let chipSeq = 0
const selectedRows = ref<number[]>([])
const dossier = ref<{ row: number; col: number } | null>(null)
const pickField = ref<string | null>(null)

const engineOverrides = computed<Record<string, any>>(() => {
  const skip_rows = [...new Set(patchChips.value.filter(c => c.kind === 'skip').flatMap(c => c.rows || []))]
  const col_binds: Record<string, string> = {}
  for (const c of patchChips.value) if (c.kind === 'bind' && c.field) col_binds[c.field] = c.letter!
  const region_ends: Record<string, number> = {}
  for (const c of patchChips.value) if (c.kind === 'end' && c.region) region_ends[c.region] = c.row!
  const out: Record<string, any> = {}
  if (skip_rows.length) out.skip_rows = skip_rows
  if (Object.keys(col_binds).length) out.col_binds = col_binds
  if (Object.keys(region_ends).length) out.region_ends = region_ends
  return out
})

const skippedRows = computed(() => engineOverrides.value.skip_rows || [])

function rowRangesLabel(rows: number[]): string {
  const sorted = [...new Set(rows)].sort((a, b) => a - b)
  const parts: string[] = []
  let start = sorted[0], prev = sorted[0]
  for (let i = 1; i <= sorted.length; i++) {
    const cur = sorted[i]
    if (cur !== prev + 1) {
      parts.push(start === prev ? `${start + 1}` : `${start + 1}-${prev + 1}`)
      start = cur
    }
    prev = cur
  }
  return parts.join('、')
}

function undoChip(id: number) {
  patchChips.value = patchChips.value.filter(c => c.id !== id)
  void reparse()
}

function clearChips() {
  patchChips.value = []
  void reparse()
}

// ── 行选（点击/拖选行号列） ──
function onToggleRow(row: number, op: 'add' | 'remove') {
  const set = new Set(selectedRows.value)
  if (op === 'add') set.add(row)
  else set.delete(row)
  selectedRows.value = [...set].sort((a, b) => a - b)
}

// ── 补丁落点操作 ──
function skipRows(rows: number[]) {
  const covered = new Set(skippedRows.value)
  const fresh = rows.filter(r => !covered.has(r))
  if (!fresh.length) {
    message.info('所选行已在跳过补丁中')
    return
  }
  patchChips.value.push({
    id: ++chipSeq, kind: 'skip', rows: fresh,
    label: `跳过第 ${rowRangesLabel(fresh)} 行`
  })
  selectedRows.value = []
  void reparse()
}

function applySkipSelected() {
  skipRows(selectedRows.value)
}

// 收口：所选首行之前结束当前「吞过头」的区域
const cutRegion = computed(() => {
  if (!selectedRows.value.length) return null
  const row = selectedRows.value[0]
  const bounds = previewData.value?.region_bounds || {}
  const hit = Object.entries(bounds)
    .filter(([, b]: any) => b.region_type !== 'static')
    .filter(([, b]: any) => b.start_row >= 0 && b.start_row <= row && b.end_row > row)
    .sort((a: any, b: any) => b[1].start_row - a[1].start_row)[0]
  if (!hit) return null
  return { regionKey: hit[0], regionName: (hit[1] as any).region_name || hit[0] }
})

function applyCutSelected() {
  const target = cutRegion.value
  if (!target || !selectedRows.value.length) return
  const row = selectedRows.value[0]
  patchChips.value = patchChips.value.filter(c => !(c.kind === 'end' && c.region === target.regionKey))
  patchChips.value.push({
    id: ++chipSeq, kind: 'end', region: target.regionKey, regionName: target.regionName, row,
    label: `${target.regionName} 收口到第 ${row + 1} 行前`
  })
  selectedRows.value = []
  void reparse()
}

// ── 字段映射（列绑定） ──
const fieldLabels = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const f of businessFields.value) m[f.key] = f.label || f.key
  return m
})

const columnRules = computed(() =>
  (parseFieldRules.value || []).filter((r: any) => r.source_type === 'column' && r.enabled))

const mappingGroups = computed(() => {
  const groups: { regionId: number; regionName: string; fields: any[] }[] = []
  for (const rule of columnRules.value) {
    const region = parseRegions.value.find((r: any) => r.id === rule.region_id)
    let g = groups.find(x => x.regionId === rule.region_id)
    if (!g) {
      g = { regionId: rule.region_id, regionName: region?.name || rule.region || '未分组', fields: [] }
      groups.push(g)
    }
    g.fields.push(rule)
  }
  return groups
})

function effectiveLetter(rule: any): string {
  const bound = engineOverrides.value.col_binds?.[rule.field_key]
  if (bound) return bound
  const region = parseRegions.value.find((r: any) => r.id === rule.region_id)
  const items = parseResult.value?.dynamic_regions?.[region?.name || rule.region] || []
  for (const it of items) {
    const t = (it._trace || []).find((x: any) => x.field_key === rule.field_key)
    if (t?.source?.col_letter) return t.source.col_letter
  }
  return rule.source_config?.col || '—'
}

// 同区域列冲突 ⚠（仅提示，不拦截）
const conflicts = computed(() => {
  const bad = new Set<string>()
  for (const g of mappingGroups.value) {
    const byLetter: Record<string, string[]> = {}
    for (const f of g.fields) {
      const letter = effectiveLetter(f)
      if (letter === '—') continue
      ;(byLetter[letter] = byLetter[letter] || []).push(f.field_key)
    }
    for (const fields of Object.values(byLetter)) {
      if (fields.length > 1) fields.forEach(k => bad.add(k))
    }
  }
  return bad
})

function togglePick(fieldKey: string) {
  pickField.value = pickField.value === fieldKey ? null : fieldKey
  selectedRows.value = []
}

function regionBoundsOf(regionId: number | null): any | null {
  const region = parseRegions.value.find((r: any) => r.id === regionId)
  if (!region) return null
  const bounds = previewData.value?.region_bounds || {}
  return bounds[region.region_key] || bounds[region.name] || null
}

// 锚定词 = 绑定列在区域数据起始行上方 1~3 行内的首个非空表头词
function anchorWordFor(rule: any, letter: string): string | null {
  const b = regionBoundsOf(rule.region_id)
  if (!b) return null
  const colIdx = letterToIdx(letter)
  const grid = previewData.value?.grid || []
  const dataStart = b.start_row + (b.skip_rows || 0)
  for (let r = dataStart - 1; r >= Math.max(0, dataStart - 3); r--) {
    const v = grid[r]?.[colIdx]
    if (v != null && String(v).trim()) return String(v).trim().slice(0, 40)
  }
  return null
}

function bindColumn(letter: string, fieldKey?: string) {
  const key = fieldKey || pickField.value
  if (!key) return
  const rule = columnRules.value.find((r: any) => r.field_key === key)
  patchChips.value = patchChips.value.filter(c => !(c.kind === 'bind' && c.field === key))
  const label = fieldLabels.value[key] || key
  const anchor = rule ? anchorWordFor(rule, letter) : null
  patchChips.value.push({
    id: ++chipSeq, kind: 'bind', field: key, letter, anchor,
    label: `${label} 取 ${letter} 列` + (anchor ? `（锚「${anchor}」）` : '')
  })
  pickField.value = null
  void reparse()
}

function onPickColumn(letter: string) {
  bindColumn(letter)
}

function regionColumnFields(regionKey: string | undefined): any[] {
  if (!regionKey) return columnRules.value.slice(0, 8)
  const region = parseRegions.value.find((r: any) => r.region_key === regionKey || r.name === regionKey)
  if (!region) return []
  return columnRules.value.filter((r: any) => r.region_id === region.id)
}

// ── 格子档案（点格看出处） ──
const dossierRegion = computed(() => {
  if (!dossier.value) return null
  const bounds = previewData.value?.region_bounds || {}
  const row = dossier.value.row
  const hit = Object.entries(bounds)
    .filter(([, b]: any) => b.region_type !== 'static')
    .filter(([, b]: any) => b.start_row >= 0 && b.start_row <= row && b.end_row > row)
    .sort((a: any, b: any) => b[1].start_row - a[1].start_row)[0]
  if (!hit) return null
  return { regionKey: hit[0], regionName: (hit[1] as any).region_name || hit[0] }
})

const dossierInfo = computed(() => {
  if (!dossier.value || !previewData.value) return null
  const { row, col } = dossier.value
  const grid = previewData.value.grid || []
  const text = grid[row]?.[col] != null ? String(grid[row][col]) : ''
  const mark = (previewData.value.cell_marks || []).find(
    (m: any) => Number(m.row) === row && Number(m.col) === col)
  const sourcedBy: { key: string; label: string; value: string }[] = []
  const sf = parseResult.value?.static_fields || {}
  for (const [field, v] of Object.entries(sf)) {
    const src = (v as any)?.source
    if (src && Number(src.row) === row && Number(src.col) === col) {
      sourcedBy.push({ key: 's' + field, label: fieldLabels.value[field] || field, value: String((v as any).value) })
    }
  }
  const dr = parseResult.value?.dynamic_regions || {}
  for (const [regionName, items] of Object.entries(dr)) {
    for (const it of items as any[]) {
      for (const t of it._trace || []) {
        const src = t.source
        if (Number(src?.row) === row && Number(src?.col) === col) {
          sourcedBy.push({
            key: `${regionName}.${t.field_key}.${src.row}`,
            label: `${regionName}·${fieldLabels.value[t.field_key] || t.field_key}`,
            value: String(t.value)
          })
        }
      }
    }
  }
  return { row, col, letter: colLetter(col), text, mark, sourcedBy }
})

function markRole(mark: any): string {
  if (mark.type === 'keyword') return `关键词（${mark.target}）`
  if (mark.type === 'extracted') return `提取值 → ${mark.target}`
  return `区域 ${mark.target}`
}

function onCellClick(cell: { row: number; col: number }) {
  dossier.value = cell
}

function colLetter(idx: number): string {
  let s = ''
  let n = idx
  while (n >= 0) {
    s = String.fromCharCode(65 + (n % 26)) + s
    n = Math.floor(n / 26) - 1
  }
  return s
}

function letterToIdx(letter: string): number {
  let n = 0
  for (const ch of letter.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64)
  return n - 1
}

// ── 重解析（预览=确认） ──
async function reparse() {
  await refreshPreview(activeSheetName.value || undefined, {
    scope: UPLOAD_SCOPE,
    overrides: engineOverrides.value
  })
}

function handleSheetChange(name: any) {
  void refreshPreview(String(name), {
    scope: UPLOAD_SCOPE,
    overrides: engineOverrides.value
  })
}

function onConfirm() {
  emit('confirm', {
    parseOverrides: engineOverrides.value
  })
}

// ── 打开弹窗：清旧遗留键 + 按使用位置绑定解析 ──
watch(
  () => [props.open, props.file],
  async ([open, file]) => {
    if (open && file) {
      patchChips.value = []
      selectedRows.value = []
      dossier.value = null
      pickField.value = null
      try { localStorage.removeItem(LEGACY_TPL_MEMO_KEY) } catch { /* ignore */ }
      await loadTemplates()
      loadBusinessFields()
      await handleFileUpload(file as File, true, undefined, { scope: UPLOAD_SCOPE })
      if (resolvedTemplateId.value != null) await loadRules(resolvedTemplateId.value)
    }
  }
)
</script>

<style scoped>
.match-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: var(--cpq-glass-bg, rgba(255, 255, 255, 0.6));
  border: 1px solid var(--cpq-border-color, rgba(255, 255, 255, 0.6));
  font-size: 12px;
  flex-wrap: wrap;
}

.match-text {
  font-weight: 600;
  color: var(--cpq-text-light);
}

.match-reason {
  color: var(--cpq-text-muted);
}

.match-warn {
  color: #d46b08;
  font-weight: 600;
}

.patch-strip {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 4px 10px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: rgba(250, 173, 20, 0.08);
  border: 1px dashed rgba(250, 173, 20, 0.5);
}

.patch-strip-label {
  font-size: 12px;
  color: #d48806;
  font-weight: 600;
}

.patch-chip {
  font-size: 12px;
}

.patch-clear {
  font-size: 12px;
  color: var(--cpq-text-muted);
  cursor: pointer;
}

.patch-clear:hover {
  color: var(--cpq-error, #ff4d4f);
}

.preview-layout {
  flex: 1;
  display: flex;
  gap: 10px;
  overflow: hidden;
  min-height: 0;
}

.preview-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.grid-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.grid-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.grid-wrap :deep(.igrid-container) {
  flex: 1;
}

.sel-toolbar {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(22, 119, 255, 0.92);
  color: #fff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  z-index: 5;
}

.sel-count {
  font-size: 12px;
  font-weight: 600;
}

.sel-toolbar :deep(.ant-btn) {
  color: #fff;
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.4);
}

.sel-toolbar :deep(.ant-btn:hover) {
  background: rgba(255, 255, 255, 0.32);
}

.preview-side {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side-card {
  flex-shrink: 0;
}

.dossier-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-light);
  word-break: break-all;
}

.dossier-pos {
  font-size: 11px;
  color: var(--cpq-text-muted);
  margin: 2px 0 8px;
}

.dossier-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 6px;
  font-size: 12px;
}

.dossier-k {
  color: var(--cpq-text-muted);
  flex-shrink: 0;
}

.dossier-sourced {
  color: var(--cpq-text-light);
  line-height: 1.6;
}

.dossier-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.mapping-group {
  margin-bottom: 10px;
}

.mapping-region {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-muted);
  margin-bottom: 4px;
}

.mapping-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 4px;
  font-size: 12px;
}

.mapping-row:hover {
  background: var(--cpq-bg-secondary, rgba(0, 0, 0, 0.03));
}

.mapping-field {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--cpq-text-light);
}

.mapping-letter {
  font-family: 'JetBrains Mono', Consolas, monospace;
  color: var(--cpq-text-muted);
}

.mapping-letter.bound {
  color: #1677ff;
  font-weight: 700;
}

.mapping-warn {
  color: #faad14;
  font-weight: 700;
}

.mapping-row.conflict {
  background: rgba(250, 173, 20, 0.08);
}

.preview-footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 12px;
}

.footer-hint {
  margin-right: auto;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

/* 左栏：修正工具（格子档案 + 字段映射） */
.preview-aside {
  width: 300px;
  flex-shrink: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
