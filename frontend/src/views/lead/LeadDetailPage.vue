<script setup lang="ts">
/** 线索详情（/leads/:leadId）—— 需求内容用 RequirementForm 只读态渲染，
 *  与商机详情页「线索登记表填好后的预览」同一组件同一设计语言；操作区在此确认/转化/驳回。 */
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import RequirementForm from '@/components/flow/RequirementForm.vue'
import { leadsApi, type LeadRecord } from '@/api/leads'
import { systemConfigApi } from '@/api/systemConfig'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canManage = computed(() => auth.can('action.lead.manage'))

const lead = ref<LeadRecord | null>(null)
const reqForm = ref<InstanceType<typeof RequirementForm> | null>(null)
const reqText = ref('')
const rejectDict = ref<Array<{ key: string; label: string; enabled: boolean }>>([])

const SOURCE_LABEL: Record<string, string> = { catalog_model: '配置完成页', catalog_general: '登记表' }
const statusMeta = computed(() => ({
  new: { label: '新线索', cls: 's-new' },
  confirmed: { label: '已确认', cls: 's-confirmed' },
  converting: { label: '转化中', cls: 's-screening' },
  assigned: { label: '已转化', cls: 's-assigned' },
  rejected: { label: '已驳回', cls: 's-rejected' },
  deleted: { label: '已删除', cls: 's-deleted' },
} as Record<string, { label: string; cls: string }>)[lead.value?.status || ''] || { label: lead.value?.status, cls: 's-new' })
const dictLabel = (key: string) => rejectDict.value.find(r => r.key === key)?.label || key

function fmtTime(iso?: string) { return iso ? iso.replace('T', ' ').slice(0, 16) : '—' }

async function load() {
  try {
    lead.value = await leadsApi.get(String(route.params.leadId))
    // 等登记表挂载（v-if="lead"）后再回填只读预览：需求原文 + 配置/KP 槽位
    await nextTick()
    reqText.value = lead.value.requirement_text || ''
    if (lead.value.config_slots) reqForm.value?.fromSlots(lead.value.config_slots as any)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '线索加载失败')
  }
}

async function loadRejectDict() {
  try {
    const list = await systemConfigApi.getValue<Array<{ key: string; label: string; enabled: boolean }>>('lead.reject_reasons')
    if (Array.isArray(list)) rejectDict.value = list
  } catch { /* 不阻塞 */ }
}

function openOpp() {
  if (lead.value?.converted_opportunity_id) router.push(`/opportunities/${lead.value.converted_opportunity_id}`)
}

// —— 转化 / 驳回（与线索池共用语义；操作入口收在详情页）——
const convertOpen = ref(false)
const bizOptions = ref<Array<{ user_id: string; name: string }>>([])
const assignee = ref('')
const converting = ref(false)
async function openConvert() {
  convertOpen.value = true
  if (!bizOptions.value.length) {
    try { bizOptions.value = (await leadsApi.businessOptions()).options } catch { message.error('业务账号加载失败') }
  }
}
async function doConvert() {
  if (!lead.value || !assignee.value) { message.warning('请选择归属业务'); return }
  converting.value = true
  try {
    const res = await leadsApi.convert(lead.value.lead_id, assignee.value)
    message.success(`已转商机 ${res.opportunity_id}，企微已通知归属业务`)
    convertOpen.value = false
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '转化失败')
  } finally { converting.value = false }
}

const rejectOpen = ref(false)
const rejectReason = ref('')
const rejectNote = ref('')
async function doReject() {
  if (!lead.value || !rejectReason.value) { message.warning('请选择驳回原因'); return }
  try {
    await leadsApi.reject(lead.value.lead_id, rejectReason.value, rejectNote.value)
    message.success('已驳回')
    rejectOpen.value = false
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '驳回失败')
  }
}

// —— 删除 / 恢复（回收站语义）：未转化线索可删；已转化背着商机溯源不可删 ——
const deleteOpen = ref(false)
async function doDelete() {
  if (!lead.value) return
  try {
    await leadsApi.remove(lead.value.lead_id)
    message.success('已移入回收站')
    deleteOpen.value = false
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}
async function doRestore() {
  if (!lead.value) return
  try {
    await leadsApi.restore(lead.value.lead_id)
    message.success('已恢复到待处理')
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '恢复失败')
  }
}

onMounted(() => { load(); loadRejectDict() })
</script>

<template>
  <div class="lead-detail">
    <header class="ld-head">
      <div class="ld-head-left">
        <a-button type="text" class="ld-back" @click="router.push('/leads')">← 线索池</a-button>
        <h1 v-if="lead">{{ lead.company || '（未留公司）' }}
          <span class="status-chip" :class="statusMeta.cls">{{ statusMeta.label }}</span>
          <span v-if="lead.dedup_count > 1" class="dedup">×{{ lead.dedup_count }} 并入</span>
        </h1>
        <div v-if="lead" class="ld-sub">
          {{ lead.lead_id }} · 来源 {{ SOURCE_LABEL[lead.source] || lead.source }} · {{ fmtTime(lead.created_at) }}
          · 联系人 {{ lead.contact_name || '—' }} · {{ lead.contact_phone }}
          <template v-if="lead.delivery_region"> · 交付地区 {{ lead.delivery_region }}</template>
          <template v-if="lead.contact_email"> · {{ lead.contact_email }}</template>
        </div>
      </div>
      <div v-if="canManage && lead && ['new', 'confirmed'].includes(lead.status)" class="ld-actions">
        <a-button danger @click="rejectOpen = true; rejectReason = ''; rejectNote = ''">驳回</a-button>
        <a-popconfirm title="删除后进回收站，可随时恢复。确认删除？" ok-text="删除" cancel-text="取消" @confirm="doDelete">
          <a-button danger type="text">删除</a-button>
        </a-popconfirm>
        <a-button type="primary" @click="openConvert">确认有效，分配转化 →</a-button>
      </div>
      <div v-else-if="canManage && lead && lead.status === 'rejected'" class="ld-actions">
        <a-popconfirm title="删除后进回收站，可随时恢复。确认删除？" ok-text="删除" cancel-text="取消" @confirm="doDelete">
          <a-button danger type="text">删除</a-button>
        </a-popconfirm>
      </div>
    </header>

    <a-spin :spinning="!lead">
      <div v-if="lead" class="ld-body">
        <!-- 需求登记预览：与商机详情页线索登记表同一组件只读态 -->
        <section class="ld-card">
          <div class="ld-card-head">
            <b>需求登记</b>
            <span class="ld-hint">客户提交原文 · {{ SOURCE_LABEL[lead.source] || lead.source }}</span>
          </div>
          <RequirementForm ref="reqForm" v-model:req-text="reqText" readonly />
          <div v-if="lead.expected_delivery" class="ld-extra">期望交期：<b>{{ lead.expected_delivery }}</b></div>
          <div v-if="(lead.attachments || []).length" class="ld-extra">
            需求附件：
            <a v-for="(att, i) in lead.attachments" :key="i" class="att-item"
               :href="leadsApi.attachmentUrl(lead.lead_id, i)" target="_blank">
              📄 {{ att.name }}（{{ (att.size / 1024).toFixed(0) }} KB）
            </a>
          </div>
        </section>

        <!-- AI 初筛：二期预留落点（一期人工；机制=llm_client 结构化评分，表已留 ai_* 字段） -->
        <section class="ld-card">
          <div class="ld-card-head"><b>AI 初筛</b><span class="ld-hint">二期预留</span></div>
          <div class="ai-placeholder">一期人工筛选。二期启用后在此展示评分分级 / 摘要 / 旗标 / 跟进切入点——表结构已预留，人工流程不变。</div>
        </section>

        <section v-if="lead.status === 'assigned' && lead.converted_opportunity_id" class="ld-card">
          <div class="ld-card-head"><b>转化结果</b></div>
          <a class="opp-link" @click="openOpp">已转商机 {{ lead.converted_opportunity_id }} → 打开商机详情</a>
        </section>
        <section v-if="lead.status === 'rejected'" class="ld-card">
          <div class="ld-card-head"><b>驳回</b></div>
          <div class="ld-reject">{{ dictLabel(lead.reject_reason) }}<template v-if="lead.reject_note"> · {{ lead.reject_note }}</template></div>
        </section>

        <section v-if="lead.status === 'deleted'" class="ld-card">
          <div class="ld-card-head"><b>回收站</b></div>
          <div class="ld-reject">该线索已删除（软删除，数据保留）。确认是误删可恢复，回到待处理重新筛选。</div>
          <div class="ld-actions" style="padding:12px 0 0">
            <a-button v-if="canManage" type="primary" @click="doRestore">恢复到待处理</a-button>
          </div>
        </section>
      </div>
    </a-spin>

    <!-- 转化弹窗 -->
    <a-modal v-model:open="convertOpen" title="转化商机 · 分配归属业务" :ok-button-props="{ disabled: !assignee }"
             :confirm-loading="converting" ok-text="确认转化" cancel-text="取消" @ok="doConvert">
      <div v-if="lead" class="cv-mini">
        <span class="status-chip s-new">新线索</span>
        <b>{{ lead.company || '（未留公司）' }}</b>
      </div>
      <div class="cv-field">
        <label>归属业务 *</label>
        <a-select v-model:value="assignee" style="width:100%" placeholder="请选择业务同事…"
                  :options="bizOptions.map(o => ({ value: o.user_id, label: o.name }))" />
      </div>
      <div class="cv-auto">
        <div>✓ 自动创建商机（客户名=公司，归属所选业务，extra_fields 记线索溯源）</div>
        <div>✓ 自动生成需求草稿（客户填的登记表原样进入，业务零重填）</div>
        <div>✓ 企微通知归属业务</div>
      </div>
    </a-modal>

    <!-- 驳回弹窗 -->
    <a-modal v-model:open="rejectOpen" title="驳回线索" ok-text="确认驳回" cancel-text="取消" @ok="doReject">
      <div class="cv-field">
        <label>驳回原因 *</label>
        <a-select v-model:value="rejectReason" style="width:100%" placeholder="请选择原因…"
                  :options="rejectDict.filter(r => r.enabled).map(r => ({ value: r.key, label: r.label }))" />
      </div>
      <div class="cv-field">
        <label>备注</label>
        <a-textarea v-model:value="rejectNote" placeholder="一句话说明（选填）" :rows="2" />
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.lead-detail { padding: 20px 24px 48px; max-width: 1080px; margin: 0 auto; }
.ld-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.ld-head-left { min-width: 0; }
.ld-back { margin: 0 0 4px -8px; color: var(--cpq-text-secondary); }
.ld-head h1 { margin: 0; font-size: var(--cpq-font-size-2xl); font-weight: 700; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ld-sub { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); margin-top: 6px; }
.ld-actions { display: flex; gap: 10px; flex-shrink: 0; }
.ld-body { display: flex; flex-direction: column; gap: 16px; }
.ld-card {
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-xl);
  background: var(--cpq-glass-card-bg); backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow); padding: 16px 20px 20px;
}
.ld-card-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.ld-card-head b { font-size: var(--cpq-font-size-lg); }
.ld-hint { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.ld-extra { margin-top: 12px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); }
.ld-extra b { color: var(--cpq-text-primary); }
.att-item { display: inline-block; margin-right: 12px; color: var(--cpq-accent-primary); }
.ai-placeholder {
  padding: 12px; border-radius: var(--cpq-radius-md); font-size: var(--cpq-font-size-xs);
  color: var(--cpq-text-muted); background: var(--cpq-overlay-w4); border: 1px dashed var(--cpq-border-primary);
  line-height: 1.7;
}
.opp-link { color: var(--cpq-accent-primary); cursor: pointer; }
.ld-reject { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); }
.status-chip {
  display: inline-block; padding: 2px 10px; font-size: var(--cpq-font-size-xs); font-weight: 600;
  border-radius: var(--cpq-radius-full); border: 1px solid transparent; white-space: nowrap;
}
.s-new { color: var(--cpq-notif-blue); background: var(--cpq-notif-blue-bg); border-color: color-mix(in srgb, var(--cpq-notif-blue) 30%, transparent); }
.s-screening { color: var(--cpq-notif-cyan); background: var(--cpq-notif-cyan-bg); border-color: color-mix(in srgb, var(--cpq-notif-cyan) 30%, transparent); }
.s-confirmed { color: var(--cpq-notif-green); background: var(--cpq-notif-green-bg); border-color: color-mix(in srgb, var(--cpq-notif-green) 35%, transparent); }
.s-assigned { color: #fff; background: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.s-rejected { color: var(--cpq-notif-red); background: var(--cpq-notif-red-bg); border-color: color-mix(in srgb, var(--cpq-notif-red) 30%, transparent); }
.dedup {
  display: inline-block; padding: 0 7px; font-size: var(--cpq-font-size-xs); font-weight: 600;
  color: var(--cpq-notif-violet); background: var(--cpq-notif-violet-bg);
  border: 1px solid color-mix(in srgb, var(--cpq-notif-violet) 30%, transparent); border-radius: var(--cpq-radius-full);
}
.cv-mini {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px; margin-bottom: 14px;
  border-radius: var(--cpq-radius-md); background: var(--cpq-overlay-a4); border: 1px solid var(--cpq-border-primary);
}
.cv-field { margin-bottom: 12px; }
.cv-field label { display: block; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); margin-bottom: 6px; }
.cv-auto { display: flex; flex-direction: column; gap: 6px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
@media (max-width: 768px) {
  .lead-detail { padding: 14px 12px 40px; }
  .ld-head h1 { font-size: var(--cpq-font-size-xl); }
}
</style>
