<template>
  <a-modal
    :open="open"
    :title="`${skill?.name || skill?.key || '工作流'} · 调用策略`"
    width="680px"
    :confirm-loading="saving"
    ok-text="保存"
    cancel-text="取消"
    @ok="save"
    @cancel="close"
  >
    <div class="srp">
      <a-alert
        type="info"
        show-icon
        message="Codex 式路由：由 LLM 根据工作流的 name + description 判断是否调用，不设置关键词规则。"
      />
      <div class="srp-field">
        <label>调用说明（description）</label>
        <a-textarea
          v-model:value="description"
          :rows="9"
          spellcheck="false"
          placeholder="例如：当用户需要配置服务器、理解硬件需求、生成候选方案或 BOM 时调用。"
        />
        <span class="srp-hint">
          这段描述会随当前同事已绑定的工作流元数据一起交给路由 LLM，用于判断是否调用该工作流。
        </span>
      </div>
      <div class="srp-foot">
        <span v-if="skill?.hit_count != null">历史命中 {{ skill.hit_count }} 次</span>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { officeApi } from '@/api/office'

const props = defineProps<{
  open: boolean
  skill: any | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', skill: any): void
}>()

const description = ref('')
const saving = ref(false)

watch(
  () => [props.open, props.skill] as const,
  ([open, skill]) => {
    if (!open) return
    description.value = String(skill?.description || '')
  },
  { immediate: true },
)

async function save() {
  if (!props.skill?.key) return
  saving.value = true
  try {
    const updated = await officeApi.updateSkill(props.skill.key, { description: description.value.trim() })
    message.success('调用策略已保存')
    emit('saved', updated)
    close()
  } catch (err: any) {
    message.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function close() {
  if (saving.value) return
  emit('close')
}
</script>

<style scoped>
.srp {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.srp-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.srp-field label {
  color: var(--cpq-text-primary);
  font-size: 13px;
}
.srp-hint {
  color: var(--cpq-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.srp-foot {
  color: var(--cpq-text-muted);
  font-size: 12px;
}
</style>
