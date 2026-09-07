<script setup lang="ts">
/**
 * 需求分析 Skill 提示词模板编辑器 —— 前端可见/可编辑，DB 唯一权威。
 * 数据源 rules.skill_prompt_template（skill_prompt_template 表）：
 *   GET  /api/system-config/skill-prompts      返回全部行（按 sort_order）
 *   PUT  /api/system-config/skill-prompts/:slot 单行落库（只写有改动的行）
 * 不再读写 system_config.skill_prompts 那把 blob，也不存在任何种子文件。
 */
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { systemConfigApi } from '@/api/systemConfig'

interface PromptRow {
  id: number
  skill_key: string
  slot_key: string
  name: string
  template: string
  enabled: boolean
  sort_order: number
}

// 仅界面 hint（不承载配置内容）；label 由 DB 行 name 提供
const HINTS: Record<string, string> = {
  data_rule: '留空=不注入数据查询规则',
  plan_rule: '用 <<STEPS>> 占位符承载流程步骤列表',
  gap_ack_template: '用 <<CLICKS>> 占位符承载已点选项',
  stream_chat_contract: '聊天正文实时展示与工具块围栏协议；修改需保持 ```tool 围栏格式',
}
const ROWS: Record<string, number> = {
  role_prompt: 14, extract_contract: 14, gap_ask_prompt: 8, price_rule_ok: 3, price_rule_no: 4,
  data_rule: 4, plan_rule: 4, gap_ack_template: 4, stream_chat_contract: 6,
}

const rows = ref<PromptRow[]>([])
const form = reactive<Record<string, string>>({})
const dirty = reactive<Record<string, boolean>>({})
const loading = ref(false)
const saving = ref(false)

function rowRows(slotKey: string): number {
  return ROWS[slotKey] || 4
}

async function load() {
  loading.value = true
  try {
    const items = await systemConfigApi.listSkillPrompts()
    rows.value = items
    for (const r of items) {
      form[r.slot_key] = String(r.template ?? '')
      dirty[r.slot_key] = false
    }
  } catch (e) {
    console.error('加载 skill_prompts 失败:', e)
    message.error('读取提示词配置失败，请检查系统配置')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const changed = rows.value.filter(r => dirty[r.slot_key])
    for (const r of changed) {
      await systemConfigApi.updateSkillPrompt(r.slot_key, { template: form[r.slot_key] ?? '' })
      dirty[r.slot_key] = false
    }
    message.success(changed.length ? `已保存 ${changed.length} 条（下次推理生效）` : '无改动')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <a-spin :spinning="loading">
    <div class="skill-prompts-panel">
      <div v-for="r in rows" :key="r.slot_key" class="prompt-field">
        <div class="prompt-label">
          <span>{{ r.name || r.slot_key }}</span>
          <span v-if="HINTS[r.slot_key]" class="prompt-hint">{{ HINTS[r.slot_key] }}</span>
          <span v-if="dirty[r.slot_key]" class="dirty-mark">●</span>
        </div>
        <a-textarea
          v-model:value="form[r.slot_key]"
          :rows="rowRows(r.slot_key)"
          @update:value="dirty[r.slot_key] = true"
        />
      </div>
      <div class="prompt-actions">
        <a-button type="primary" :loading="saving" @click="save">保存设置</a-button>
        <span class="prompt-note">这些提示词由 DB 唯一承载（rules.skill_prompt_template），前端直接读写落库。</span>
      </div>
    </div>
  </a-spin>
</template>

<style scoped>
.skill-prompts-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0;
}
.prompt-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.prompt-label {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-weight: 600;
  color: #333;
}
.prompt-hint {
  font-size: 12px;
  color: #999;
  font-weight: 400;
}
.dirty-mark {
  color: #f5222d;
  font-size: 12px;
}
.prompt-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.prompt-note {
  font-size: 12px;
  color: #999;
}
</style>
