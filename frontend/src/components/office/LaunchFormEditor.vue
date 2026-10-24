<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { reasoningFlowApi } from '@/api/reasoningFlow'
import type { LaunchFormField } from '@/components/assistant/LaunchFormPanel.vue'

/**
 * 启动表单编辑器（配置者视角）：工作流管理卡片 ⋮ 菜单进入。
 * schema 落流配置独立列 launch_form（通用底座，字段用户可增删改排序）；
 * 保存走 /launch-form 专用端点（画布保存物理碰不到这一列）。
 * 右侧实时预览 = launcher 渲染效果。
 * 「从节点契约同步」：identify 节点目标层的字段契约（key/label/必填）一键带入
 * ——反问点与开工单字段同源，改契约后重按一次即同步（显式动作，不做隐式自动生成）。
 */
const props = defineProps<{ open: boolean; skillKey: string; name: string }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

const TYPES: Array<{ value: LaunchFormField['type']; label: string }> = [
  { value: 'text', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'select', label: '下拉' },
  { value: 'file', label: '文件' },
  { value: 'textarea', label: '多行文本' },
]

const fields = ref<LaunchFormField[]>([])
const loading = ref(false)
const saving = ref(false)
let flowConfigs: Record<string, any> = {}

watch(() => props.open, async (v) => {
  if (!v) return
  loading.value = true
  try {
    const r = await reasoningFlowApi.get(props.skillKey)
    const lf = (r.flow as any)?.launch_form
    fields.value = Array.isArray(lf?.fields) ? JSON.parse(JSON.stringify(lf.fields)) : []
    flowConfigs = (r.flow as any)?.node_configs || {}
  } catch {
    message.warning('流配置读取失败')
    fields.value = []
    flowConfigs = {}
  } finally {
    loading.value = false
  }
})

/** 契约字段 → 表单字段映射：key/label/required 原样，类型按语义推断。 */
function fieldFromContract(f: Record<string, any>): LaunchFormField | null {
  const key = String(f.key || '').trim()
  if (!key) return null
  const type: LaunchFormField['type'] = key === 'attachment' ? 'file'
    : key === 'margin_pct' ? 'number' : 'text'
  return { key, type, label: String(f.label || key), required: !!f.ask }
}

/** 从 identify 节点目标层契约同步：契约字段逐个带入（已有同 key 字段跳过，其余保留）。 */
function syncFromContract() {
  const art = flowConfigs?.identify?.target?.artifacts?.[0]
  const contractFields: any[] = Array.isArray(art?.fields) ? art.fields : []
  if (!contractFields.length) {
    message.info('identify 节点还没有字段契约：先在画布节点抽屉 → 目标层配置字段')
    return
  }
  const existingKeys = new Set(fields.value.map((f) => f.key))
  const added: LaunchFormField[] = []
  for (const cf of contractFields) {
    const nf = fieldFromContract(cf)
    if (nf && !existingKeys.has(nf.key)) {
      fields.value.push(nf)
      existingKeys.add(nf.key)
      added.push(nf)
    }
  }
  if (added.length) {
    message.success(`已从节点契约带入 ${added.length} 个字段：${added.map((f) => f.label).join('、')}`)
  } else {
    message.info('契约字段都已在表单里（同 key 跳过）')
  }
}

function addField(type: LaunchFormField['type']) {
  fields.value.push({ key: `field_${Date.now().toString(36)}`, type, label: '新字段', required: false })
}
function move(i: number, d: -1 | 1) {
  const j = i + d
  if (j < 0 || j >= fields.value.length) return
  const arr = fields.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}
function optionsText(f: LaunchFormField): string {
  return Array.isArray(f.options) ? f.options.join('/') : String(f.options || '')
}
function defaultOf(f: LaunchFormField): string {
  const d = (f.default || '').trim()
  const m = d.match(/^\{(.+)\}$/)
  return m ? `{${m[1]}}` : d
}

async function save() {
  const keys = new Set<string>()
  for (const f of fields.value) {
    if (!f.key?.trim() || !f.label?.trim()) {
      message.warning('每个字段都需要 key 和显示名')
      return
    }
    if (keys.has(f.key)) {
      message.warning(`字段 key 重复：${f.key}`)
      return
    }
    keys.add(f.key)
  }
  saving.value = true
  try {
    const schema = fields.value.length
      ? { fields: fields.value.map((f) => {
          const o: any = { key: f.key, type: f.type, label: f.label }
          if (f.required) o.required = true
          if (f.default?.trim()) o.default = f.default.trim()
          if (f.type === 'select') o.options = Array.isArray(f.options) ? f.options : optionsText(f).split('/').map((x) => x.trim()).filter(Boolean)
          return o
        }) }
      : null
    await reasoningFlowApi.saveLaunchForm(props.skillKey, schema)
    message.success(fields.value.length ? '启动表单已保存' : '启动表单已清空（恢复自由对话）')
    emit('saved')
    emit('close')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-drawer :open="props.open" :title="`启动表单 · ${props.name}`" width="720" @close="emit('close')">
    <p style="font-size:12px;color:var(--cpq-text-secondary,#4e5969);margin-top:0;">
      「+」选中该工作流时按此表单渲染开工单；字段可增删改排序，底座提供 5 种通用类型。
      清空全部字段 = 恢复自由对话。提交时拼装结构化首条消息，跳过表单则行为与现状一致。
      <a style="margin-left:6px;cursor:pointer;" @click="syncFromContract">从节点契约同步字段</a>
    </p>
    <a-spin :spinning="loading">
      <div
        v-for="(f, i) in fields"
        :key="f.key + i"
        class="field-row"
      >
        <span class="row-idx">{{ i + 1 }}</span>
        <input v-model="f.label" class="fi" placeholder="显示名（用户看到的）">
        <select v-model="f.type" class="fi">
          <option v-for="t in TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <label class="chk"><input v-model="f.required" type="checkbox">必填</label>
        <input v-model="f.default" class="fi" placeholder="默认值" :disabled="f.type === 'file'">
        <span class="row-ops">
          <button class="op" title="上移" :disabled="i === 0" @click="move(i, -1)">↑</button>
          <button class="op" title="下移" :disabled="i === fields.length - 1" @click="move(i, 1)">↓</button>
          <button class="op del" title="删除字段" @click="fields.splice(i, 1)">✕</button>
        </span>
        <input v-if="f.type === 'select'" v-model="f.options" class="fi wide" placeholder="下拉选项，用 / 分隔，如：scheme / internal">
      </div>
      <div class="add-row">
        <span style="font-size:12px;color:var(--cpq-text-muted,#86909c);align-self:center;">添加字段：</span>
        <button v-for="t in TYPES" :key="t.value" class="add-chip" @click="addField(t.value)">＋ {{ t.label }}</button>
      </div>

      <h4 style="margin:20px 0 8px;font-size:13px;">实时预览（launcher 渲染效果）</h4>
      <div class="pv-form">
        <div v-for="f in fields" :key="'pv' + f.key + f.type" class="pv-field" :class="{ full: f.type === 'file' || f.type === 'textarea' }">
          <label>{{ f.label }}<span v-if="f.required" style="color:#e5534b;">*</span></label>
          <div v-if="f.type === 'file'" class="pv-file">点击或拖入附件</div>
          <textarea v-else-if="f.type === 'textarea'" rows="2" disabled />
          <select v-else-if="f.type === 'select'" disabled><option>{{ optionsText(f) || '—' }}</option></select>
          <input v-else type="text" disabled :placeholder="defaultOf(f)">
        </div>
        <p v-if="!fields.length" style="font-size:12px;color:var(--cpq-text-muted,#86909c);margin:0;">
          （无字段 = 「+」选中后保持现状自由输入）
        </p>
      </div>
    </a-spin>
    <template #footer>
      <a-button @click="emit('close')">取消</a-button>
      <a-button type="primary" :loading="saving" @click="save">保存</a-button>
    </template>
  </a-drawer>
</template>

<style scoped>
.field-row { display: grid; grid-template-columns: 22px 1fr 90px 52px 100px auto; gap: 8px;
  align-items: center; padding: 8px; border: 1px solid var(--cpq-border-primary, rgba(22,119,255,0.10));
  border-radius: var(--cpq-radius-md, 6px); margin-bottom: 8px; background: var(--cpq-bg-elevated, #fff); }
.row-idx { text-align: center; font-size: 12px; color: var(--cpq-text-muted, #86909c); }
.fi { width: 100%; border: 1px solid var(--cpq-border-light, rgba(22,119,255,0.16)); border-radius: 4px;
  padding: 4px 8px; font-size: 12px; font-family: inherit; color: var(--cpq-text-primary, #1d2129);
  background: var(--cpq-bg-elevated, #fff); }
.fi.wide { grid-column: 2 / -1; }
.chk { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--cpq-text-secondary, #4e5969); }
.row-ops { display: flex; gap: 4px; }
.op { border: 1px solid var(--cpq-border-light, rgba(22,119,255,0.16)); background: transparent;
  border-radius: 4px; width: 22px; height: 22px; font-size: 11px; cursor: pointer; color: var(--cpq-text-secondary, #4e5969); }
.op.del:hover { color: #e5534b; border-color: #e5534b; }
.op:disabled { opacity: .35; cursor: default; }
.add-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.add-chip { border: 1px dashed var(--cpq-border-light, rgba(22,119,255,0.16)); background: transparent;
  border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer;
  color: var(--cpq-text-secondary, #4e5969); font-family: inherit; }
.add-chip:hover { color: var(--cpq-accent-primary, #1677FF); border-color: var(--cpq-accent-primary, #1677FF); }
.pv-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; padding: 12px;
  border: 1px solid var(--cpq-border-primary, rgba(22,119,255,0.10)); border-radius: 8px;
  background: var(--cpq-overlay-w4, rgba(22,119,255,0.04)); }
.pv-field { display: flex; flex-direction: column; gap: 4px; }
.pv-field.full { grid-column: 1 / -1; }
.pv-field label { font-size: 12px; color: var(--cpq-text-secondary, #4e5969); }
.pv-field input, .pv-field select, .pv-field textarea { border: 1px solid var(--cpq-border-light, rgba(22,119,255,0.16));
  border-radius: 6px; padding: 6px 10px; font-size: 13px; font-family: inherit; }
.pv-file { border: 1.5px dashed var(--cpq-border-light, rgba(22,119,255,0.16)); border-radius: 6px;
  padding: 12px; text-align: center; font-size: 12px; color: var(--cpq-text-muted, #86909c); }
</style>
