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
      <button type="button" class="hq-btn hq-cancel" @click="answer({ selections: ['取消'] })">取消</button>
      <button type="button" class="hq-btn hq-primary" @click="answer({ selections: ['确认执行'] })">确认执行</button>
    </div>

    <!-- choice：单选 + Other 逃生门。视觉已并入单问确认卡形态（2026-11-04 退役旧 radio 卡样式）：
         序号键选项行 + 描述 + 推荐胶囊 + Other；答案仍走问答协议槽（query_id 结构化回流）。 -->
    <template v-else-if="query.kind === 'choice' && interactive">
      <div class="hq-opts">
        <button
          v-for="(o, i) in query.options"
          :key="i"
          type="button"
          class="hq-opt"
          :class="{ picked: picked === o.label, rec: o.recommended }"
          @click="picked = picked === o.label ? '' : o.label"
        >
          <span class="hq-key">{{ picked === o.label ? '✓' : Number(i) + 1 }}</span>
          <span class="hq-opt-main">
            <span class="hq-opt-label">{{ o.label }}<i v-if="o.recommended" class="hq-rec">推荐</i></span>
            <span v-if="o.description" class="hq-opt-desc">{{ o.description }}</span>
          </span>
        </button>
        <button
          type="button"
          class="hq-opt hq-escape"
          :class="{ picked: picked === '__other__' }"
          @click="picked = picked === '__other__' ? '' : '__other__'"
        >
          <span class="hq-key">⋯</span>
          <span class="hq-opt-main">
            <span class="hq-opt-label">Other</span>
            <span class="hq-opt-desc">都不合适？说说你的想法</span>
          </span>
        </button>
        <input
          v-if="picked === '__other__'"
          v-model="otherText"
          class="hq-other"
          type="text"
          placeholder="说说你的想法，回车提交"
          @keyup.enter="submitChoice"
        />
      </div>
      <div class="hq-actions">
        <span class="hq-foot-hint">选择一项，或选 Other 自由输入</span>
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
import { assistantApi, type AssistantQueryAnswer } from '@/api/assistant'

const props = withDefaults(defineProps<{
  message?: { kind?: string; data?: string; content?: string }
  optionInteractive?: boolean
  threadId?: string
}>(), {
  message: undefined,
  optionInteractive: true,
  threadId: '',
})

const emit = defineEmits<{ (e: 'answer', payload: AssistantQueryAnswer): void }>()

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

async function answer(answerPart: Omit<AssistantQueryAnswer, 'query_id'>) {
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
  display: inline-flex; align-items: center; justify-content: center; font-size: var(--cpq-font-size-sm);
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
.hq-opts { display: flex; flex-direction: column; padding: 0 0 4px; }
.hq-opt { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 12px; cursor: pointer;
  border: 0; border-top: 1px solid transparent; background: transparent; text-align: left;
  color: var(--cpq-text-primary); font: inherit; transition: background .15s ease; }
.hq-opt + .hq-opt { border-top: 1px solid var(--cpq-overlay-w6, rgba(255,255,255,.08)); }
.hq-opt:hover { background: var(--cpq-overlay-a10, rgba(22,119,255,.10)); }
.hq-opt.picked { background: var(--cpq-overlay-a8, rgba(22,119,255,.08));
  box-shadow: inset 2px 0 0 var(--cpq-accent-primary, #1677ff); }
.hq-opt.picked .hq-key { border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff); }
.hq-escape .hq-opt-label { color: var(--cpq-text-secondary, #a6adb4); }
.hq-key { flex: none; min-width: 20px; height: 20px; padding: 0 4px;
  border-radius: var(--cpq-radius-sm); border: 1px solid var(--cpq-overlay-w10, rgba(255,255,255,.14));
  display: inline-flex; align-items: center; justify-content: center;
  font-size: var(--cpq-font-size-xs); font-weight: 600; color: var(--cpq-text-secondary, #a6adb4); }
.hq-opt:hover .hq-key { border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff); }
.hq-opt-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.hq-opt-label { font-size: 13px; line-height: 1.4; color: var(--cpq-text-primary); }
.hq-rec { font-style: normal; margin-left: 6px; padding: 0 6px; font-size: 10.5px; line-height: 18px;
  vertical-align: middle; border-radius: 999px; color: #6ea8ff;
  background: rgba(22, 119, 255, 0.14); border: 1px solid rgba(22, 119, 255, 0.35); }
.hq-opt.rec { border-color: rgba(22, 119, 255, 0.45); }
.hq-opt-desc { font-size: var(--cpq-font-size-sm); line-height: 1.4;
  color: var(--cpq-text-muted, #8c8c8c); word-break: break-word; }
.hq-other { margin: 0 12px 6px; height: 28px; padding: 0 10px; font-size: 12.5px;
  border-radius: var(--cpq-radius-sm); border: 1px solid var(--cpq-overlay-w14, rgba(255,255,255,.2));
  background: transparent; color: var(--cpq-text-primary); outline: none; }
.hq-other:focus { border-color: var(--cpq-accent-primary, #1677ff); }
.hq-foot-hint { margin-right: auto; font-size: 11.5px; color: var(--cpq-text-muted, #8c8c8c); }
.hq-fields { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
.hq-field { display: flex; flex-direction: column; gap: 4px; }
.hq-field-label { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary, #a6adb4); }
.hq-input { height: 32px; padding: 0 10px; font-size: 13px; border-radius: var(--cpq-radius-sm);
  border: 1px solid var(--cpq-overlay-w14, rgba(255,255,255,.22));
  background: var(--cpq-overlay-w6, rgba(255,255,255,.08)); color: var(--cpq-text-primary);
  outline: none; }
.hq-input:focus { border-color: var(--cpq-accent-primary, #1677ff); }
.hq-done { padding: 10px 12px; font-size: var(--cpq-font-size-sm); font-weight: 600; color: #16a34a; }
</style>
