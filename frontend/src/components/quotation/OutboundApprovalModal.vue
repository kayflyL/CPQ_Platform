<script setup lang="ts">
/**
 * 外发审批发起弹窗（公共组件）——报价工作台导出闸 / 详情页发送闸共用。
 * 打开时拉取审批状态（毛利 vs 红线、内容指纹、路由预览、pending/rejected/stale 提示），
 * 提交 = createOutboundApproval。批准=对内容指纹的外发许可，改价失配自动失效重批。
 */
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { portalApi } from '@/api/portal'
import type { OutboundApprovalState } from '@/api/portal'

const props = defineProps<{
  open: boolean
  opportunityId: string
  quotationId: string
  quotationLabel?: string
}>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'submitted', approval: Record<string, any>): void
}>()

const state = ref<OutboundApprovalState | null>(null)
const note = ref('')
const submitting = ref(false)
const loadFailed = ref(false)

watch(() => props.open, async (v) => {
  if (!v) return
  note.value = ''
  state.value = null
  loadFailed.value = false
  try {
    state.value = await portalApi.outboundApprovalStatus(props.opportunityId, props.quotationId)
  } catch {
    loadFailed.value = true
  }
})

async function submit() {
  submitting.value = true
  try {
    const res = await portalApi.createOutboundApproval(props.opportunityId, props.quotationId, note.value.trim())
    const assigned = res.approval?.assigned_name
    message.success(assigned
      ? `已提交总监审批（责任人 ${assigned}），批准后即可导出/发送；期间报价单锁定`
      : '已提交审批（广播全体审批人，先到先批），批准后即可导出/发送')
    emit('submitted', res.approval)
    emit('update:open', false)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '提交审批失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <a-modal
    :open="open"
    title="导出/发送需总监审批"
    :width="`min(480px, 94vw)`"
    @cancel="emit('update:open', false)"
  >
    <div class="oam-body">
      <template v-if="loadFailed">
        <div class="oam-warn">审批状态拉取失败，请关闭后重试。</div>
      </template>
      <template v-else-if="!state">
        <div class="oam-muted">正在加载审批状态…</div>
      </template>
      <template v-else>
        <div class="oam-grid">
          <span class="k">报价单</span>
          <span>{{ quotationLabel || quotationId }}</span>
          <span class="k">综合毛利率</span>
          <span>
            <b :class="{ 'oam-hot': state.margin_pct != null && state.margin_pct < state.threshold }">
              {{ state.margin_pct != null ? state.margin_pct.toFixed(2) + '%' : '—' }}
            </b>
            <span v-if="state.threshold" class="oam-muted">　审批红线 {{ state.threshold }}%</span>
          </span>
          <span class="k">内容指纹</span>
          <span><span class="oam-hash">{{ state.content_hash || '—' }}</span><span class="oam-muted">　批后改价自动失效重批</span></span>
        </div>

        <div v-if="state.state === 'pending'" class="oam-warn">
          该报价单已有待审批的外发申请（已等待 {{ Math.max(1, Math.round(state.waited_hours)) }} 小时，责任人
          {{ state.approval?.assigned_name || '全体审批人' }}），无需重复提交。
        </div>
        <div v-if="state.margin_pct != null && state.margin_pct < state.threshold" class="oam-warn">
          ⚠ 综合毛利率低于审批红线——批准后才能导出/发送，导出即冻结。
        </div>
        <div v-if="state.state === 'stale'" class="oam-warn">上次批准后报价内容已变更，需重新审批。</div>
        <div v-if="state.state === 'rejected'" class="oam-warn">
          上次审批被驳回<span v-if="state.approval?.comment">：{{ state.approval.comment }}</span>。可调整后重新提交。
        </div>
        <div v-if="state.state === 'approved'" class="oam-ok">
          该报价单已有有效外发许可，可直接导出/发送；如需重新审批（例如许可过期）再提交。
        </div>

        <div class="oam-route">
          将指派 → <b>{{ state.route?.assigned_name || '全体审批人（先到先批）' }}</b>
          <span class="oam-muted">（{{ state.route?.basis_text || '调度规则' }}）</span>
        </div>

        <a-textarea
          v-if="state.state !== 'pending' && state.state !== 'approved'"
          v-model:value="note"
          :rows="2"
          placeholder="审批说明（可选，总监可见）"
        />
      </template>
    </div>
    <template #footer>
      <a-button @click="emit('update:open', false)">关闭</a-button>
      <a-button
        v-if="state && !['pending', 'approved'].includes(state.state)"
        type="primary"
        :loading="submitting"
        @click="submit"
      >提交审批</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.oam-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
  font-size: 13px;
}
.oam-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 16px;
}
.oam-grid .k { color: var(--cpq-text-muted); }
.oam-hot { color: var(--cpq-accent-danger, #FF6B6B); }
.oam-muted { color: var(--cpq-text-muted); }
.oam-hash {
  font-family: Consolas, monospace;
  font-size: var(--cpq-font-size-sm);
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.06));
  border-radius: var(--cpq-radius-xs);
  padding: 1px 6px;
}
.oam-warn {
  background: var(--cpq-warn-surface, rgba(250, 173, 20, 0.10));
  border: 1px solid var(--cpq-warn-border, rgba(250, 173, 20, 0.30));
  border-radius: var(--cpq-radius-sm);
  padding: 8px 12px;
  color: var(--cpq-notif-amber, #F4D28A);
  line-height: 1.6;
}
.oam-ok {
  background: var(--cpq-notif-green-bg, rgba(82, 201, 160, 0.18));
  border-radius: var(--cpq-radius-sm);
  padding: 8px 12px;
  color: var(--cpq-notif-green, #52C9A0);
  line-height: 1.6;
}
.oam-route {
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.08));
  border: 1px solid var(--cpq-overlay-a20, rgba(22, 119, 255, 0.20));
  border-radius: var(--cpq-radius-sm);
  padding: 8px 12px;
  line-height: 1.6;
}
</style>
