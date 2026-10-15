<script setup lang="ts">
// Result change modal: requires a one-line note for any result change;
// lost/expired also pick a loss reason from an editable dictionary.
// Confirm calls POST /opportunities/{id}/result-change which persists
// attribution fields and auto-posts a status-change comment to the feed.
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { projectApi } from '@/api'
import { systemConfigApi } from '@/api/systemConfig'
import { RESULT_OPTIONS, resultLabel } from '@/constants/opportunityResult'
import { useAuthStore } from '@/store/auth'

interface LossReason { key: string; label: string; enabled: boolean }

const props = defineProps<{
  open: boolean
  opportunityId: string
  current: string
  target: string
  reasons: LossReason[]
}>()

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'changed', opp: Record<string, any>): void
  (e: 'reasons-updated', list: LossReason[]): void
}>()

const auth = useAuthStore()
// backend enforces require_admin on the config PUT; this only gates the entry
const canManage = computed(() => auth.can('page.settings.users'))

const saving = ref(false)
const note = ref('')
const reasonKeys = ref<string[]>([])
const managing = ref(false)
const draftList = ref<LossReason[]>([])
const newLabel = ref('')

watch(() => props.open, (v) => {
  if (v) {
    note.value = ''
    reasonKeys.value = []
    managing.value = false
  }
})

const targetLabel = computed(() => resultLabel(props.target))
const reasonOptions = computed(() =>
  props.reasons.filter(r => r.enabled).map(r => ({ value: r.key, label: r.label }))
)
const showReason = computed(() => props.target === 'lost' || props.target === 'expired')

function tagColor(val: string) {
  return RESULT_OPTIONS.find(o => o.value === val)?.color ?? 'default'
}

function close() {
  emit('update:open', false)
}

async function confirm() {
  if (!note.value.trim()) {
    message.warning('请填写一句话说明')
    return
  }
  if (props.target === 'lost' && !reasonKeys.value.length) {
    message.warning('已丢标必须选择未成单原因')
    return
  }
  saving.value = true
  try {
    const res = await projectApi.resultChange(props.opportunityId, {
      result: props.target,
      note: note.value.trim(),
      loss_reason_keys: showReason.value ? reasonKeys.value : [],
    })
    emit('changed', res.opportunity)
    close()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '状态变更失败')
  } finally {
    saving.value = false
  }
}

// ── dictionary management (admin) ──

function startManage() {
  draftList.value = props.reasons.map(r => ({ ...r }))
  newLabel.value = ''
  managing.value = true
}

function addReason() {
  const label = newLabel.value.trim()
  if (!label) return
  if (draftList.value.some(r => r.label === label)) {
    message.warning('原因已存在')
    return
  }
  draftList.value.push({ key: `custom_${Date.now().toString(36)}`, label, enabled: true })
  newLabel.value = ''
}

function removeReason(r: LossReason) {
  draftList.value = draftList.value.filter(x => x.key !== r.key)
}

async function saveDict() {
  const cleaned = draftList.value
    .map(r => ({ key: r.key, label: (r.label || '').trim(), enabled: !!r.enabled }))
    .filter(r => r.label)
  if (!cleaned.length) {
    message.warning('至少保留一个原因')
    return
  }
  saving.value = true
  try {
    const res: any = await systemConfigApi.set('opportunity.loss_reasons', cleaned, 'json')
    const list: LossReason[] = res?.value ?? cleaned
    emit('reasons-updated', list)
    managing.value = false
    message.success('原因字典已保存')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败，需要管理员权限')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :title="`将商机状态改为「${targetLabel}」`"
    :width="'min(460px, 92vw)'"
    :mask-closable="false"
    ok-text="确认变更"
    cancel-text="取消"
    :confirm-loading="saving"
    @ok="confirm"
    @cancel="close"
  >
    <template v-if="!managing">
      <div class="rcm-block">
        <div class="rcm-label">状态</div>
        <div class="rcm-transition">
          <a-tag :color="tagColor(current)">{{ resultLabel(current) }}</a-tag>
          <span class="rcm-arrow">→</span>
          <a-tag :color="tagColor(target)">{{ targetLabel }}</a-tag>
        </div>
        <div v-if="showReason" class="rcm-block rcm-block-inner">
          <div class="rcm-label">{{ target === 'lost' ? '未成单原因 *' : '未成单原因（选填）' }}</div>
          <a-checkbox-group v-model:value="reasonKeys" class="rcm-reason-group" :options="reasonOptions" />
        </div>
        <div class="rcm-block rcm-block-inner">
          <div class="rcm-label">说一句 *</div>
          <a-textarea
            v-model:value="note"
            :rows="3"
            :maxlength="200"
            show-count
            placeholder="一句话记录这次变更的进展或原因，会同步到协作动态"
          />
        </div>
        <div v-if="canManage" class="rcm-manage-toggle">
          <a @click="startManage">管理原因字典</a>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="rcm-dict">
        <div v-if="!draftList.length" class="rcm-dict-empty">暂无原因，请在下方添加</div>
        <div v-for="r in draftList" :key="r.key" class="rcm-dict-row">
          <a-input v-model:value="r.label" class="rcm-dict-label" />
          <a-switch v-model:checked="r.enabled" size="small" />
          <a-popconfirm title="删除后历史商机将回退显示 key，建议改用禁用" @confirm="removeReason(r)">
            <a class="rcm-dict-del">删除</a>
          </a-popconfirm>
        </div>
        <div class="rcm-dict-row">
          <a-input v-model:value="newLabel" class="rcm-dict-label" placeholder="新原因" @press-enter="addReason" />
          <a-button size="small" @click="addReason">添加</a-button>
        </div>
        <div class="rcm-dict-save">
          <a-button size="small" type="primary" :loading="saving" @click="saveDict">保存字典</a-button>
        </div>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.rcm-block {
  margin-bottom: var(--cpq-space-4);
}
.rcm-block-inner {
  margin-top: var(--cpq-space-4);
}
.rcm-label {
  margin-bottom: var(--cpq-space-2);
  font-size: 12px;
  color: var(--cpq-text-secondary, #888);
  }
.rcm-transition {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
}
.rcm-arrow {
  color: var(--cpq-text-secondary, #888);
}
.rcm-manage-toggle {
  text-align: right;
}
.rcm-reason-group {
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-2);
  align-items: flex-start;
}
.rcm-dict-row {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
  margin-bottom: var(--cpq-space-2);
}
.rcm-dict-label {
  flex: 1;
}
.rcm-dict-del {
  color: var(--cpq-danger, #ff4d4f);
}
.rcm-dict-save {
  margin-top: var(--cpq-space-4);
  text-align: right;
}
</style>
