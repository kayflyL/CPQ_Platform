<template>
  <div v-if="query" class="hq-card" :class="'hq-' + query.kind">
    <div class="hq-head">
      <span class="hq-badge">{{ kindIcon }}</span>
      <span class="hq-title">{{ query.question?.title }}</span>
    </div>
    <pre v-if="query.question?.detail" class="hq-detail">{{ query.question.detail }}</pre>
    <p v-if="query.question?.hint" class="hq-hint">{{ query.question.hint }}</p>

    <!-- consent：授权问询（确认执行/取消） -->
    <div v-if="query.kind === 'consent' && interactive" class="hq-actions">
      <button type="button" class="hq-btn hq-cancel" @click="answer(['取消'])">取消</button>
      <button type="button" class="hq-btn hq-primary" @click="answer(['确认执行'])">确认执行</button>
    </div>

    <!-- choice：单选 + Other 逃生门 -->
    <template v-else-if="query.kind === 'choice' && interactive">
      <div class="hq-opts">
        <label v-for="(o, i) in query.options" :key="i" class="hq-opt" :class="{ picked: picked === o.label }">
          <input v-model="picked" type="radio" name="hq-choice" :value="o.label" />
          <span class="hq-opt-main">
            <span class="hq-opt-label">{{ o.label }}<i v-if="o.recommended" class="hq-rec">推荐</i></span>
            <span v-if="o.description" class="hq-opt-desc">{{ o.description }}</span>
          </span>
        </label>
        <label class="hq-opt" :class="{ picked: picked === '__other__' }">
          <input v-model="picked" type="radio" name="hq-choice" value="__other__" />
          <span class="hq-opt-main"><span class="hq-opt-label">Other</span></span>
        </label>
        <input
          v-if="picked === '__other__'"
          v-model="otherText"
          class="hq-other"
          type="text"
          placeholder="说说你的想法…"
          @keyup.enter="submitChoice"
        />
      </div>
      <div class="hq-actions">
        <button type="button" class="hq-btn hq-primary" :disabled="!canChoice" @click="submitChoice">回答</button>
      </div>
    </template>

    <!-- form：字段表单 -->
    <template v-else-if="query.kind === 'form' && interactive">
      <div class="hq-fields">
        <div v-for="f in query.fields" :key="f.key" class="hq-field">
          <label class="hq-field-label">{{ f.label }}</label>
          <input
            v-model="values[f.key]"
            class="hq-input"
            :type="f.type === 'number' ? 'number' : 'text'"
            :placeholder="f.placeholder || ''"
            @keyup.enter="submitForm"
          />
        </div>
      </div>
      <div class="hq-actions">
        <button type="button" class="hq-btn hq-primary" :disabled="!canForm" @click="submitForm">提交</button>
      </div>
    </template>

    <div v-if="!interactive" class="hq-done">✓ 已回答{{ answeredText ? '：' + answeredText : '' }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * HumanQueryCard —— 问答协议的 schema 驱动渲染器（唯一组件吃全部形状）：
 * consent（授权问询：确认执行/取消，action 绑定直达执行）/ choice（单选+Other 逃生门，
 * 推荐标记）/ form（字段表单）。答案经 POST /answers 按 query_id 结构化回流，
 * 不走文本匹配。旧 input_options/input_form 消息仍由 AskCard/InputFormCard 重放。
 */
import { computed, reactive, ref } from 'vue'
import { assistantApi } from '@/api/assistant'

const props = withDefaults(defineProps<{
  message?: { kind?: string; data?: string; content?: string }
  optionInteractive?: boolean
  threadId?: string
}>(), {
  message: undefined,
  optionInteractive: true,
  threadId: '',
})

const emit = defineEmits<{ (e: 'answer', payload: Record<string, any>): void }>()

const query = computed<null | any>(() => {
  if (props.message?.kind !== 'query' || !props.message?.data) return null
  try {
    const d = JSON.parse(props.message.data)
    return d?.query_id && d?.kind ? d : null
  } catch {
    return null
  }
})

const kindIcon = computed(() =>
  query.value?.kind === 'consent' ? '✓' : query.value?.kind === 'choice' ? '☑' : '✎')

const submitted = ref(false)
const answeredText = ref('')
const interactive = computed(() => !!props.optionInteractive && !submitted.value)

const picked = ref('')
const otherText = ref('')
const values = reactive<Record<string, string>>({})
const canChoice = computed(() => picked.value === '__other__'
  ? !!otherText.value.trim() : !!picked.value)
const canForm = computed(() =>
  (query.value?.fields || []).some((f: any) => String(values[f.key] ?? '').trim() !== ''))

async function answer(answerPart: { selections?: string[]; values?: Record<string, string>; note?: string }) {
  if (!query.value || submitted.value) return
  if (!props.threadId) return
  const payload = { query_id: query.value.query_id, ...answerPart }
  submitted.value = true
  answeredText.value = [...(answerPart.selections || []),
    ...Object.entries(answerPart.values || {}).map(([k, v]) => `${k}=${v}`)].join('；')
  emit('answer', payload)
  try {
    await assistantApi.answers.create(props.threadId, payload)
  } catch (e: any) {
    submitted.value = false
    answeredText.value = ''
    throw e
  }
}

function submitChoice() {
  if (!canChoice.value) return
  if (picked.value === '__other__') {
    answer({ selections: [], note: otherText.value.trim() })
  } else {
    answer({ selections: [picked.value] })
  }
}

function submitForm() {
  if (!canForm.value) return
  const vals: Record<string, string> = {}
  for (const f of query.value?.fields || []) {
    const v = String(values[f.key] ?? '').trim()
    if (v !== '') vals[f.key] = v
  }
  answer({ values: vals })
}
</script>

<style scoped>
.hq-card {
  max-width: 100%;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w4, rgba(255,255,255,.05));
  overflow: hidden;
}
.hq-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w8, rgba(255,255,255,.10));
  background: var(--cpq-overlay-a6, rgba(22,119,255,.06)); }
.hq-badge { flex: none; width: 18px; height: 18px; border-radius: var(--cpq-radius-sm);
  display: inline-flex; align-items: center; justify-content: center; font-size: 12px;
  color: var(--cpq-accent-primary, #1677ff); border: 1px solid var(--cpq-accent-primary, #1677ff); }
.hq-title { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); }
.hq-detail { margin: 10px 12px 0; padding: 8px 10px; font-family: inherit; font-size: 12.5px;
  line-height: 1.7; color: var(--cpq-text-secondary, #a6adb4); white-space: pre-wrap;
  background: var(--cpq-overlay-w4, rgba(255,255,255,.04));
  border-radius: var(--cpq-radius-sm); }
.hq-hint { margin: 8px 12px 0; font-size: 11.5px; color: var(--cpq-text-muted, #8c8c8c); }
.hq-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 10px 12px; }
.hq-btn { padding: 5px 18px; border-radius: var(--cpq-radius-sm); font-size: 12.5px;
  font-weight: 600; cursor: pointer; border: 1px solid var(--cpq-overlay-w14, rgba(255,255,255,.2));
  background: transparent; color: var(--cpq-text-primary); transition: opacity .15s ease; }
.hq-btn:disabled { opacity: .4; cursor: default; }
.hq-primary { border-color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-accent-primary, #1677ff); color: #fff; }
.hq-opts { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px 0; }
.hq-opt { display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; cursor: pointer;
  border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.12));
  border-radius: var(--cpq-radius-sm); transition: border-color .15s ease; }
.hq-opt.picked { border-color: var(--cpq-accent-primary, #1677ff); }
.hq-opt-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.hq-opt-label { font-size: 12.5px; font-weight: 600; color: var(--cpq-text-primary); }
.hq-rec { font-style: normal; margin-left: 6px; padding: 1px 6px; font-size: 10.5px;
  border-radius: 999px; color: var(--cpq-accent-primary, #1677ff);
  border: 1px solid var(--cpq-accent-primary, #1677ff); }
.hq-opt-desc { font-size: 11.5px; color: var(--cpq-text-secondary, #a6adb4); }
.hq-other { margin: 6px 0 0 24px; height: 30px; padding: 0 10px; font-size: 12.5px;
  border-radius: var(--cpq-radius-sm); border: 1px solid var(--cpq-overlay-w14, rgba(255,255,255,.2));
  background: transparent; color: var(--cpq-text-primary); outline: none; }
.hq-other:focus { border-color: var(--cpq-accent-primary, #1677ff); }
.hq-fields { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
.hq-field { display: flex; flex-direction: column; gap: 4px; }
.hq-field-label { font-size: 12px; color: var(--cpq-text-secondary, #a6adb4); }
.hq-input { height: 32px; padding: 0 10px; font-size: 13px; border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-overlay-w14, rgba(255,255,255,.22));
  background: var(--cpq-overlay-w6, rgba(255,255,255,.08)); color: var(--cpq-text-primary);
  outline: none; }
.hq-input:focus { border-color: var(--cpq-accent-primary, #1677ff); }
.hq-done { padding: 10px 12px; font-size: 12px; font-weight: 600; color: #16a34a; }
</style>
