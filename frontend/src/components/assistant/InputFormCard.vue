<template>
  <div v-if="form" class="if-card">
    <div class="if-head">
      <span class="if-badge">✎</span>
      <span class="if-title">{{ form.title }}</span>
    </div>
    <div class="if-body">
      <div v-for="f in form.fields" :key="f.key" class="if-field">
        <label class="if-label">{{ f.label }}</label>
        <input
          v-model="values[f.key]"
          class="if-input"
          :type="f.type === 'number' ? 'number' : 'text'"
          :placeholder="f.placeholder || ''"
          :disabled="!interactive || submitted"
          @keyup.enter="submit"
        />
      </div>
      <p v-if="form.hint" class="if-hint">{{ form.hint }}</p>
    </div>
    <div class="if-foot">
      <template v-if="!submitted">
        <span class="if-foot-hint">提交后 AI 继续处理</span>
        <button type="button" class="if-submit" :disabled="!canSubmit" @click="submit">提交</button>
      </template>
      <template v-else>
        <span class="if-done">✓ 已提交</span>
        <span class="if-done-vals">{{ submittedText }}</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 会话输入卡（kind='input_form'）：ask_user_card 工具的渲染端。
 * 分工（2026-10-22 用户定调）：AI 决定何时发卡、发什么字段（ask_user_card 调用）；
 * 系统保证弹出与渲染；用户提交后以「label」=值 文本回流对话，AI 据此继续。
 */
import { computed, reactive, ref } from 'vue'

const props = withDefaults(defineProps<{
  message?: { kind?: string; data?: string; content?: string }
  optionInteractive?: boolean
}>(), {
  message: undefined,
  optionInteractive: true,
})

const emit = defineEmits<{ (e: 'submit-form', text: string): void }>()

const form = computed<null | { title: string; hint: string; fields: Array<{ key: string; label: string; placeholder: string; type: string }> }>(() => {
  if (props.message?.kind !== 'input_form' || !props.message?.data) return null
  try {
    const data = JSON.parse(props.message.data)
    const f = data?.form
    if (!f || !Array.isArray(f.fields) || !f.fields.length) return null
    return {
      title: String(f.title || '请填写'),
      hint: String(f.hint || ''),
      fields: f.fields.map((x: any) => ({
        key: String(x.key || ''),
        label: String(x.label || x.key || ''),
        placeholder: String(x.placeholder || ''),
        type: String(x.type || 'text'),
      })),
    }
  } catch {
    return null
  }
})

const values = reactive<Record<string, string>>({})
const submitted = ref(false)
const submittedText = ref('')

const interactive = computed(() => !!props.optionInteractive && !submitted.value)

const canSubmit = computed(() =>
  interactive.value && (form.value?.fields || []).some((f) => String(values[f.key] ?? '').trim() !== ''))

function submit() {
  if (!canSubmit.value || !form.value) return
  const parts = form.value.fields
    .map((f) => ({ f, v: String(values[f.key] ?? '').trim() }))
    .filter((x) => x.v !== '')
    .map((x) => `「${x.f.label}」${x.v}`)
  if (!parts.length) return
  submittedText.value = parts.join('；')
  submitted.value = true
  emit('submit-form', submittedText.value)
}
</script>

<style scoped>
.if-card {
  max-width: 82%;
  min-width: 260px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.12));
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  overflow: hidden;
}
.if-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w8, rgba(255,255,255,.10));
  background: var(--cpq-overlay-a6, rgba(22,119,255,.06));
}
.if-badge {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: var(--cpq-radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--cpq-accent-primary, #1677ff);
  border: 1px solid var(--cpq-accent-primary, #1677ff);
}
.if-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.if-body {
  padding: 10px 12px 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.if-field {
  display: flex;
  align-items: center;
  gap: 10px;
}
.if-label {
  flex: none;
  min-width: 88px;
  font-size: 12.5px;
  color: var(--cpq-text-secondary, #a6adb4);
  text-align: right;
}
.if-input {
  flex: 1;
  height: 30px;
  border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  background: transparent;
  color: var(--cpq-text-primary);
  font-size: 12.5px;
  padding: 0 10px;
  outline: none;
}
.if-input:focus {
  border-color: var(--cpq-accent-primary, #1677ff);
}
.if-input:disabled {
  opacity: .5;
}
.if-hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--cpq-text-muted, #8c8c8c);
}
.if-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-top: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.08));
}
.if-foot-hint {
  font-size: 11.5px;
  color: var(--cpq-text-muted, #8c8c8c);
}
.if-submit {
  flex: none;
  padding: 4px 16px;
  border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s ease;
}
.if-submit:disabled {
  opacity: .4;
  cursor: default;
}
.if-done {
  flex: none;
  font-size: 12px;
  color: #16a34a;
  font-weight: 600;
}
.if-done-vals {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--cpq-text-primary, inherit);
  font-weight: 600;
}
</style>
