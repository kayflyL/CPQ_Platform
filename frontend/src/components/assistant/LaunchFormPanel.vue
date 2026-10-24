<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

/**
 * LaunchFormPanel —— 工作流启动表单的通用渲染底座。
 * schema 来自流配置 graph.launch_form（配置者在管理面可视化编辑）；
 * 提交 = emit submit({values, files})，由装填方拼装结构化首条消息。
 * 本组件不认识任何具体工作流——底座通用，字段即一切。
 */
export interface LaunchFormField {
  key: string
  type: 'text' | 'number' | 'select' | 'file' | 'textarea'
  label: string
  required?: boolean
  default?: string
  options?: string[] | string
}

const props = defineProps<{
  schema: { fields?: LaunchFormField[] }
  /** 默认值占位解析（如 {当前用户姓名} → 操作者姓名），由装填方提供 */
  defaults?: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'submit', payload: { values: Record<string, string>; files: File[] }): void
  (e: 'skip'): void
}>()

const fields = computed<LaunchFormField[]>(() => (Array.isArray(props.schema?.fields) ? props.schema.fields : []))

function defaultOf(f: LaunchFormField): string {
  const d = (f.default || '').trim()
  const m = d.match(/^\{(.+)\}$/)
  if (m && props.defaults?.[m[1]]) return props.defaults[m[1]]
  return d
}

const values = reactive<Record<string, string>>({})
for (const f of fields.value) if (f.type !== 'file') values[f.key] = defaultOf(f)
// fields 是静态 schema（装填期不变），初始化一次即可

const filesByField = reactive<Record<string, File[]>>({})
const dragOver = reactive<Record<string, boolean>>({})
const missing = ref<Set<string>>(new Set())

function optionsOf(f: LaunchFormField): string[] {
  if (Array.isArray(f.options)) return f.options
  return String(f.options || '').split('/').map((s) => s.trim()).filter(Boolean)
}

function pickFiles(f: LaunchFormField, e: Event) {
  const input = e.target as HTMLInputElement
  onFiles(f, Array.from(input.files || []))
}
function onDrop(f: LaunchFormField, e: DragEvent) {
  dragOver[f.key] = false
  const dropped = Array.from(e.dataTransfer?.files || [])
  if (dropped.length) onFiles(f, dropped)
}
function onFiles(f: LaunchFormField, list: File[]) {
  if (!list.length) return
  filesByField[f.key] = list.slice(0, 3) // 单字段最多 3 个附件（与聊天框上传同额度语义）
}

function fileName(f: LaunchFormField): string {
  const list = filesByField[f.key] || []
  return list.map((x) => x.name).join('、')
}

function onSubmit() {
  const miss: string[] = []
  const valuesOut: Record<string, string> = {}
  const files: File[] = []
  for (const f of fields.value) {
    if (f.type === 'file') {
      const list = filesByField[f.key] || []
      if (f.required && !list.length) miss.push(f.label)
      files.push(...list)
      continue
    }
    const v = String(values[f.key] ?? '').trim()
    if (f.required && !v) miss.push(f.label)
    if (v) valuesOut[f.label] = v // 值按 label 装配（拼装首条消息直接人话可读）
  }
  missing.value = new Set(miss)
  if (miss.length) return
  emit('submit', { values: valuesOut, files })
}
</script>

<template>
  <div class="launch-form">
    <div class="lf-grid">
      <div v-for="f in fields" :key="f.key" class="lf-field" :class="{ full: f.type === 'file' || f.type === 'textarea' }">
        <label>{{ f.label }}<span v-if="f.required" class="req">*</span></label>

        <div v-if="f.type === 'file'" class="lf-file" :class="{ has: fileName(f), over: dragOver[f.key] }"
             @click="($event.currentTarget as HTMLElement).querySelector('input')?.click()"
             @dragover.prevent="dragOver[f.key] = true" @dragleave="dragOver[f.key] = false"
             @drop.prevent="onDrop(f, $event)">
          <input type="file" multiple hidden @change="pickFiles(f, $event)">
          <template v-if="fileName(f)">📄 {{ fileName(f) }}（点击或拖入更换）</template>
          <template v-else>点击或拖入附件</template>
        </div>

        <textarea v-else-if="f.type === 'textarea'" v-model="values[f.key]" rows="2" />
        <select v-else-if="f.type === 'select'" v-model="values[f.key]">
          <option value="">—</option>
          <option v-for="o in optionsOf(f)" :key="o" :value="o">{{ o }}</option>
        </select>
        <input v-else-if="f.type === 'number'" v-model="values[f.key]" type="number">
        <input v-else v-model="values[f.key]" type="text">

        <span v-if="missing.has(f.label)" class="lf-miss">必填</span>
      </div>
    </div>
    <div class="lf-actions">
      <button type="button" class="lf-btn primary" @click="onSubmit">开始办理 →</button>
    </div>
  </div>
</template>

<style scoped>
.launch-form { background: var(--cpq-glass-card-bg, rgba(255,255,255,0.9)); border: 1px solid var(--cpq-border-primary, rgba(22,119,255,0.10));
  border-radius: var(--cpq-radius-lg, 8px); box-shadow: var(--cpq-glass-card-shadow, 0 10px 30px rgba(22,119,255,0.10));
  padding: var(--cpq-space-4, 16px); margin-bottom: var(--cpq-space-3, 12px); }
.lf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cpq-space-3, 12px) var(--cpq-space-4, 16px); }
.lf-field { display: flex; flex-direction: column; gap: 4px; }
.lf-field.full { grid-column: 1 / -1; }
.lf-field label { font-size: 12px; color: var(--cpq-text-secondary, #4e5969); }
.req { color: #e5534b; margin-left: 2px; }
.lf-miss { font-size: 11px; color: #e5534b; }
.lf-field input[type=text], .lf-field input[type=number], .lf-field select, .lf-field textarea {
  border: 1px solid var(--cpq-border-light, rgba(22,119,255,0.16)); border-radius: var(--cpq-radius-md, 6px);
  padding: 6px 10px; font-size: 13px; font-family: inherit; color: var(--cpq-text-primary, #1d2129);
  background: var(--cpq-bg-elevated, #fff); outline: none; }
.lf-field input:focus, .lf-field select:focus, .lf-field textarea:focus { border-color: var(--cpq-accent-primary, #1677FF); }
.lf-file { border: 1.5px dashed var(--cpq-border-light, rgba(22,119,255,0.16)); border-radius: var(--cpq-radius-md, 6px);
  padding: var(--cpq-space-3, 12px); text-align: center; font-size: 12px; color: var(--cpq-text-muted, #86909c);
  cursor: pointer; }
.lf-file.over { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.lf-file.has { border-style: solid; color: var(--cpq-accent-success, #22c55e); background: rgba(34,197,94,0.06); }
.lf-actions { display: flex; justify-content: flex-end; margin-top: var(--cpq-space-3, 12px); }
.lf-btn { border: none; background: var(--cpq-accent-primary, #1677FF); color: #fff; border-radius: var(--cpq-radius-md, 6px);
  padding: 6px 16px; font-size: 13px; cursor: pointer; font-family: inherit; }
</style>
