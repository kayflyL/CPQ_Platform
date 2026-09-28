<script setup lang="ts">
/**
 * 工具卡（注册表 agent_tool_specs + 人类展示层的统一扑克卡）。
 * 两处复用：AI 工具目录页（可编辑目录态）与推理流节点抽屉工具层（可交互选态）。
 * 卡面 = 人类层（中文名 + 一句话）；详情弹窗分区展示 人话详解 / 模型契约 / 参数表 / 被引用。
 * 点卡面 = 查看详情；挂载/移除走卡底按钮；目录态可编辑文案（DB 覆盖层，模型契约受宪法校验）。
 */
import { computed, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { assistantApi } from '@/api/assistant'
import { toolCategoryLabel } from '@/constants/toolMeta'

const props = withDefaults(defineProps<{
  /** 工具条目（目录接口原样条目，或抽屉 toolOptions 项归一后的形状） */
  tool: {
    name: string
    category?: string
    display_name?: string
    one_liner?: string
    summary?: string
    description?: string
    parameters?: Record<string, any>
    default_enabled?: boolean
    custom?: string[]
  }
  /** idle=目录/待选 selected=已挂载 locked=机制锁死 */
  state?: 'idle' | 'selected' | 'locked'
  /** 引用该工具的节点标签（「被引用」徽标；抽屉态不传） */
  usage?: string[]
  /** 紧凑态（抽屉）：卡面更矮，底行为挂载按钮 */
  compact?: boolean
  /** 可交互（抽屉选态）：卡底/弹窗出现挂载·移除按钮 */
  interactive?: boolean
  /** 可编辑文案（目录态）：弹窗出现「编辑文案」与「恢复默认」 */
  editable?: boolean
  /** 机制锁因（locked 卡详情里展示） */
  lockNote?: string
}>(), {
  state: 'idle',
  usage: () => [],
  compact: false,
  interactive: false,
  editable: false,
  lockNote: '',
})

const emit = defineEmits<{
  (e: 'toggle', name: string): void
  (e: 'updated', tool: any): void
}>()

const detailOpen = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = reactive({ display_name: '', one_liner: '', description: '', model_brief: '' })

/** 缩写章：fill_requirement → FR */
const initials = computed(() => {
  const parts = String(props.tool.name || '').split('_').filter(Boolean)
  return (parts.slice(0, 2).map((p) => p[0]).join('') || '?').toUpperCase()
})

const category = computed(() => String(props.tool.category || ''))
const customSet = computed(() => new Set(props.tool.custom || []))

/** 参数明细（弹窗表）：名称/类型/必填/取值与说明 */
const paramRows = computed(() => {
  const p = props.tool.parameters
  if (!p || !p.properties) return []
  const required: string[] = Array.isArray(p.required) ? p.required : []
  return Object.entries(p.properties).map(([key, prop]) => {
    const pd = (prop || {}) as Record<string, any>
    const enums = Array.isArray(pd.enum) && pd.enum.length ? pd.enum.join(' | ') : ''
    const note = [enums, pd.description].filter(Boolean).join('　')
    return { key, type: pd.type || '', required: required.includes(key), note }
  })
})

const usageLine = computed(() =>
  props.usage.length ? `被 ${props.usage.join(' · ')} 引用` : '')

function onToggle() {
  emit('toggle', props.tool.name)
}

function startEdit() {
  form.display_name = props.tool.display_name || ''
  form.one_liner = props.tool.one_liner || ''
  form.description = props.tool.description || ''
  form.model_brief = props.tool.summary || ''
  editing.value = true
}

async function saveEdit() {
  saving.value = true
  try {
    const updated = await assistantApi.tools.updateText(props.tool.name, { ...form })
    message.success('工具文案已保存')
    editing.value = false
    emit('updated', updated)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function resetText() {
  saving.value = true
  try {
    const updated = await assistantApi.tools.resetText(props.tool.name)
    message.success('已恢复默认文案')
    editing.value = false
    emit('updated', updated)
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '恢复失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div
    class="tool-card"
    :class="[`is-${state}`, { 'tc-compact': compact }]"
    role="button"
    tabindex="0"
    @click="detailOpen = true"
    @keydown.enter="detailOpen = true"
  >
    <div class="tc-top">
      <span class="tc-mono" :class="`cat-${category}`">{{ initials }}</span>
      <span v-if="category" class="tc-cat" :class="`cat-${category}`">{{ toolCategoryLabel(category) }}</span>
    </div>
    <div class="tc-title">
      <span class="tc-display">{{ tool.display_name || tool.name }}</span>
    </div>
    <div class="tc-name">{{ tool.name }}</div>
    <div class="tc-summary">{{ tool.one_liner || tool.summary || tool.description }}</div>
    <div class="tc-foot">
      <template v-if="interactive && state !== 'locked'">
        <span v-if="state === 'selected'" class="tc-mounted">已挂载</span>
        <button
          type="button"
          class="tc-act"
          :class="state === 'selected' ? 'tc-act--remove' : 'tc-act--mount'"
          @click.stop="onToggle"
        >{{ state === 'selected' ? '移除' : '＋ 挂载' }}</button>
      </template>
      <span v-else-if="state === 'locked'" class="tc-locknote">🔒 机制必需</span>
      <span v-else class="tc-meta">{{ usageLine || `${paramRows.length} 个参数` }}</span>
    </div>

    <a-modal
      v-model:open="detailOpen"
      :title="tool.display_name ? `${tool.display_name}（${tool.name}）` : tool.name"
      :footer="null"
      width="920px"
      class="tool-detail-modal"
      @cancel="editing = false"
    >
      <!-- ── 查看态：双栏（左=详解+模型契约，右=参数+引用）── -->
      <template v-if="!editing">
        <div class="td-tags">
          <a-tag v-if="category" :class="`cat-${category}`">{{ toolCategoryLabel(category) }}</a-tag>
          <a-tag color="success" v-if="tool.default_enabled !== false">默认启用</a-tag>
          <a-tag v-else>需勾选启用</a-tag>
          <a-tag v-if="state === 'selected'" color="blue">已挂载本节点</a-tag>
          <a-tag v-else-if="state === 'locked'">🔒 机制必需</a-tag>
          <a-tag v-if="customSet.size" color="orange">文案已自定义</a-tag>
        </div>
        <p v-if="tool.one_liner" class="td-summary">{{ tool.one_liner }}</p>

        <div class="td-cols">
          <div class="td-col">
            <template v-if="tool.description && tool.description !== tool.one_liner">
              <div class="td-sec">详解（给人看的）</div>
              <p class="td-desc">{{ tool.description }}</p>
            </template>

            <template v-if="tool.summary">
              <div class="td-sec">模型契约<span class="td-sec-note">每回合注入给 AI · 编辑会直接改变 AI 行为</span></div>
              <p class="td-desc td-brief">{{ tool.summary }}</p>
            </template>
          </div>

          <div class="td-col">
            <template v-if="paramRows.length">
              <div class="td-sec">参数（{{ paramRows.length }}）<span class="td-sec-note">说明为模型契约原文</span></div>
              <table class="td-params">
                <thead>
                  <tr><th class="td-p-name">参数</th><th class="td-p-type">类型</th><th class="td-p-req">必填</th><th>取值 / 说明</th></tr>
                </thead>
                <tbody>
                  <tr v-for="row in paramRows" :key="row.key">
                    <td class="td-p-name">{{ row.key }}</td>
                    <td class="td-p-type">{{ row.type }}</td>
                    <td class="td-p-req">{{ row.required ? '✓' : '' }}</td>
                    <td>{{ row.note || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </template>

            <template v-if="usage.length">
              <div class="td-sec">被引用</div>
              <div class="td-usage">
                <span v-for="u in usage" :key="u" class="td-usage-chip">{{ u }}</span>
              </div>
            </template>

            <p v-if="state === 'locked' && lockNote" class="td-locknote">🔒 {{ lockNote }}</p>
          </div>
        </div>

        <div class="td-actions">
          <a-button
            v-if="interactive && state !== 'locked'"
            :type="state === 'selected' ? 'default' : 'primary'"
            @click="onToggle(); detailOpen = false"
          >{{ state === 'selected' ? '移除挂载' : '＋ 挂载到本节点' }}</a-button>
          <a-button v-if="editable" @click="startEdit">编辑文案</a-button>
          <a-button @click="detailOpen = false">关闭</a-button>
        </div>
      </template>

      <!-- ── 编辑态 ── -->
      <template v-else>
        <div class="td-edit-hint">
          中文名与一句话给人看；「模型契约」每回合注入 AI 大脑——保存受宪法校验，
          祈使/流程类措辞（怎么做、先调谁）属左栏任务规则，写这里会被拒。
        </div>
        <div class="td-field">
          <label>中文名{{ customSet.has('display_name') ? ' ·已自定义' : '' }}</label>
          <a-input v-model:value="form.display_name" placeholder="如：配件检索" :maxlength="30" />
        </div>
        <div class="td-field">
          <label>一句话{{ customSet.has('one_liner') ? ' ·已自定义' : '' }}</label>
          <a-textarea v-model:value="form.one_liner" :rows="2" :maxlength="160" show-count
            placeholder="做什么。什么时候用。" />
        </div>
        <div class="td-field">
          <label>详解（给人看的）{{ customSet.has('description') ? ' ·已自定义' : '' }}</label>
          <a-textarea v-model:value="form.description" :rows="7" :maxlength="4000" />
        </div>
        <div class="td-field">
          <label>模型契约（注入 AI）{{ customSet.has('model_brief') ? ' ·已自定义' : '' }}</label>
          <a-textarea v-model:value="form.model_brief" :rows="5" :maxlength="4000" show-count />
        </div>
        <div class="td-actions">
          <a-popconfirm
            v-if="customSet.size"
            title="恢复整套默认文案？当前自定义（含模型契约）将全部丢弃。"
            @confirm="resetText"
          >
            <a-button danger :loading="saving">恢复默认</a-button>
          </a-popconfirm>
          <a-button @click="editing = false">取消</a-button>
          <a-button type="primary" :loading="saving" @click="saveEdit">保存</a-button>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.tool-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 14px 14px 12px;
  min-height: 148px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: 12px;
  background: var(--cpq-glass-1-bg);
  box-shadow: var(--cpq-shadow-sm);
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  outline: none;
  min-width: 0;
}
.tool-card:hover,
.tool-card:focus-visible {
  transform: translateY(-2px);
  box-shadow: var(--cpq-shadow-md, 0 4px 12px rgba(0, 0, 0, 0.12));
}
.tool-card.is-selected {
  border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-glass-2-bg);
}
.tool-card.is-locked {
  border-style: dashed;
  background: transparent;
}
.tc-compact { min-height: 128px; padding: 11px 12px 10px; gap: 5px; }

.tc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tc-mono {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; flex-shrink: 0;
  border-radius: 9px;
  font-size: 13px; font-weight: 700; letter-spacing: 0.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.tc-mono.cat-selection { background: rgba(22, 119, 255, 0.16); color: #6ea8ff; }
.tc-mono.cat-data { background: rgba(114, 46, 209, 0.16); color: #b37feb; }
.tc-mono.cat-cost { background: rgba(250, 140, 22, 0.16); color: #ffc069; }
.tc-mono.cat-quote { background: rgba(82, 196, 26, 0.16); color: #95de64; }
.tc-mono:not([class*="cat-"]) { background: var(--cpq-glass-2-bg); color: var(--cpq-text-secondary); }

.tc-cat {
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10.5px;
  line-height: 1.7;
  color: var(--cpq-text-secondary);
  background: var(--cpq-glass-2-bg);
  border: 1px solid var(--cpq-border-primary);
}

.tc-title { display: flex; align-items: baseline; gap: 6px; }
.tc-display {
  font-size: 14px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tc-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--cpq-text-muted);
  word-break: break-all;
}
.tc-summary {
  flex: 1;
  font-size: 12px;
  line-height: 1.55;
  color: var(--cpq-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tc-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  min-height: 24px;
}
.tc-mounted {
  font-size: 11.5px;
  color: var(--cpq-accent-primary, #6ea8ff);
}
.tc-act {
  padding: 1px 10px;
  border-radius: 999px;
  border: 1px solid var(--cpq-border-primary);
  background: transparent;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--cpq-text-secondary);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.tc-act--mount {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.tc-act--mount:hover { background: rgba(22, 119, 255, 0.10); }
.tc-act--remove:hover { border-color: #ff7875; color: #ff7875; }
.tc-locknote, .tc-meta {
  font-size: 11px;
  color: var(--cpq-text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ── 详情弹窗 ── */
.td-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.td-summary { margin: 0 0 6px; font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.td-cols {
  display: grid;
  grid-template-columns: 11fr 9fr;
  gap: 2px 20px;
  align-items: start;
}
.td-col { min-width: 0; }
.td-sec {
  margin: 14px 0 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.td-sec-note { margin-left: 8px; font-size: 11px; font-weight: 400; color: var(--cpq-text-muted); }
.td-desc { margin: 0; font-size: 12.5px; line-height: 1.7; color: var(--cpq-text-secondary); white-space: pre-wrap; }
.td-brief {
  padding: 8px 10px;
  border-left: 3px solid var(--cpq-accent-primary, #1677ff);
  border-radius: 4px;
  background: var(--cpq-glass-2-bg);
}
.td-params {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.td-params th, .td-params td {
  padding: 5px 8px;
  border: 1px solid var(--cpq-border-primary);
  text-align: left;
  vertical-align: top;
  line-height: 1.5;
}
.td-params th { color: var(--cpq-text-secondary); font-weight: 600; background: var(--cpq-glass-2-bg); }
.td-p-name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: nowrap; }
.td-p-type, .td-p-req { white-space: nowrap; color: var(--cpq-text-muted); }
.td-usage { display: flex; flex-wrap: wrap; gap: 6px; }
.td-usage-chip {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  color: var(--cpq-text-secondary);
  background: var(--cpq-glass-1-bg);
  border: 1px solid var(--cpq-border-primary);
}
.td-locknote {
  margin: 12px 0 0;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px dashed var(--cpq-border-primary);
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.td-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

/* ── 编辑态 ── */
.td-edit-hint {
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px dashed var(--cpq-border-primary);
  font-size: 12px;
  line-height: 1.6;
  color: var(--cpq-text-secondary);
}
.td-field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.td-field label { font-size: 12px; color: var(--cpq-text-primary); }
</style>
