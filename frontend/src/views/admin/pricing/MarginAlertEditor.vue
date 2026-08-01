<script setup lang="ts">
/** 利润率告警配置（独立策略 type=margin_alert）—— 工作台低毛利弹窗的开关+门槛+文案 SSOT。
 *  与保底封顶（引擎 clamp）解耦：保底封顶管目标毛利率的夹取区间，这里管「毛利低于多少弹什么提示」。
 *  未持久化（id=null）保存时 create，已有则 update；保存后 invalidatePricingRules 让工作台即时读新值。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { strategyApi } from '@/api/strategies'
import { usePricingRulesStore } from '@/stores/pricingRules'
import { DEFAULT_MARGIN_ALERT, type MarginAlertBody } from '@/constants/pricingMeta'

const store = usePricingRulesStore()

const alertOpen = ref(false)
const saving = ref(false)
// 编辑态（modal 内双向绑定）
const form = ref<MarginAlertBody>({ ...DEFAULT_MARGIN_ALERT })
const formId = ref<number | null>(null)

// 当前生效配置（卡片摘要用）
const state = computed(() => store.marginAlertState)

watch(alertOpen, (v) => {
  if (!v) return
  form.value = { ...state.value.body }
  formId.value = state.value.id
})

async function save() {
  if (!form.value.title.trim()) { message.warning('请填写告警标题'); return }
  if (!form.value.content.trim()) { message.warning('请填写告警正文'); return }
  saving.value = true
  try {
    const body = {
      enabled: !!form.value.enabled,
      threshold: Number.isFinite(Number(form.value.threshold)) ? Number(form.value.threshold) : DEFAULT_MARGIN_ALERT.threshold,
      title: form.value.title.trim(),
      content: form.value.content.trim(),
    }
    if (formId.value) {
      await strategyApi.update(formId.value, { body, name: '利润率告警' })
    } else {
      await strategyApi.create({ domain: 'pricing', type: 'margin_alert', name: '利润率告警', scope: null, body, status: 'active' })
    }
    message.success('告警配置已保存（工作台即时生效）')
    store.invalidatePricingRules()
    await store.ensurePricingRules()
    alertOpen.value = false
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// 正文预览：替换占位符给个示例（5.60% 低于门槛）
const previewContent = computed(() => {
  const c = state.value.body.content
  return c.replace(/\$\{margin\}/g, '5.60').replace(/\$\{threshold\}/g, String(state.value.body.threshold))
})
</script>

<template>
  <div class="ma-card">
    <div class="ma-head">
      <div class="ma-title">
        <span class="ma-icon">⚠️</span>
        <span>利润率告警</span>
        <a-tag v-if="state.body.enabled" color="orange" class="ma-tag">已启用 · 门槛 {{ state.body.threshold }}%</a-tag>
        <a-tag v-else class="ma-tag">已关闭</a-tag>
      </div>
      <a-button size="small" type="primary" ghost @click="alertOpen = true">编辑</a-button>
    </div>
    <div class="ma-body">
      <div class="ma-line"><span class="ma-label">标题</span>{{ state.body.title }}</div>
      <div class="ma-line"><span class="ma-label">正文</span>{{ previewContent }}</div>
      <p class="ma-hint">工作台综合毛利率低于门槛时弹此提示（只警告不锁价、不自动改价）。与保底封顶解耦——保底封顶管引擎目标毛利的夹取区间，这里管弹窗阈值与文案。</p>
    </div>

    <a-modal :open="alertOpen" title="配置利润率告警" :width="560" :confirm-loading="saving"
             ok-text="保存" cancel-text="取消" @ok="save" @cancel="alertOpen = false">
      <a-form layout="vertical" style="margin-top: 12px">
        <a-form-item label="启用告警">
          <a-switch v-model:checked="form.enabled" />
          <span class="ma-form-hint">关闭后工作台不再弹利润率告警</span>
        </a-form-item>
        <a-form-item label="告警门槛（综合毛利率）">
          <a-input-number v-model:value="form.threshold" :min="0" :max="80" :step="1" style="width: 200px">
            <template #addonAfter>%</template>
          </a-input-number>
          <span class="ma-form-hint">低于此值触发告警</span>
        </a-form-item>
        <a-form-item label="告警标题">
          <a-input v-model:value="form.title" placeholder="如：利润率低于告警线" />
        </a-form-item>
        <a-form-item label="告警正文（支持占位符 ${margin}=当前毛利率 / ${threshold}=门槛）">
          <a-textarea v-model:value="form.content" :rows="3" placeholder="如：当前综合毛利率 ${margin}% 低于告警线 ${threshold}%，建议线下走特价审批，系统仅作记录。" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.ma-card {
  border: 1px solid var(--cpq-glass-border, rgba(0,0,0,.08));
  border-radius: var(--cpq-radius-md, 12px);
  background: var(--cpq-overlay-w8, rgba(255,255,255,.72));
  padding: 12px 16px;
}
.ma-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ma-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); }
.ma-icon { font-size: 16px; }
.ma-tag { margin-left: 4px; }
.ma-body { margin-top: 8px; }
.ma-line { font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.7; }
.ma-label { display: inline-block; width: 40px; color: var(--cpq-text-muted); }
.ma-hint { font-size: 11px; color: var(--cpq-text-muted); margin: 8px 0 0; }
.ma-form-hint { margin-left: 12px; font-size: 12px; color: var(--cpq-text-muted); }
</style>
