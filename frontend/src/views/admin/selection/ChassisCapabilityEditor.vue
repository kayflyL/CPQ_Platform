<script setup lang="ts">
/**
 * 机箱能力档案编辑器 —— 选型配置「🏗 机箱能力」标签。
 *
 * 把原散落前端硬编码的「机箱物理上能装什么」(电源槽数 / 后面板槽位布局 / GPU 槽上限 / TDP 上限)
 * 提到 base_config 表，在此按机箱可编辑——兑现「一切前端可配置、拒绝硬编码」。
 *
 * 数据走 baseConfigApi.list/get/update（后端 base_config_repo 已开放 psu_bays/rear_slots/gpu_slots/max_tdp）。
 * rear_slots = [{name, cap}]，与 utils/partFit.slotCapOf / L6ChassisConfig.rearSlotDefs 同形。
 */
import { ref, reactive, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { baseConfigApi, type BaseConfig, type RearSlot } from '@/api/serverConfig'
import { DEFAULT_REAR_SLOTS, GPU_ARCH_OPTIONS } from '@/constants/chassisMeta'

interface CapabilityForm {
  psu_bays: number
  gpu_slots: number
  max_tdp: number | null
  gpu_arch_default: string
  rear_slots: RearSlot[]
}

const configs = ref<BaseConfig[]>([])
const loading = ref(false)
const editOpen = ref(false)
const editing = ref<BaseConfig | null>(null)
const saving = ref(false)
const form = reactive<CapabilityForm>({ psu_bays: 2, gpu_slots: 0, max_tdp: null, gpu_arch_default: 'none', rear_slots: [] })

async function load() {
  loading.value = true
  try {
    const res = await baseConfigApi.list()
    configs.value = res.configs || []
  } catch { configs.value = [] } finally { loading.value = false }
}
onMounted(load)

function rearSummary(rs: RearSlot[] | undefined): string {
  if (!rs || !rs.length) return '—'
  return rs.map(s => `${s.name}×${s.cap}`).join(' · ')
}
function gpuArchLabel(v?: string | null): string {
  return GPU_ARCH_OPTIONS.find(o => o.value === v)?.label || '未配'
}

function openEdit(c: BaseConfig) {
  editing.value = c
  const rs = (c.rear_slots && c.rear_slots.length ? c.rear_slots : DEFAULT_REAR_SLOTS).map(s => ({ name: s.name, cap: s.cap }))
  Object.assign(form, { psu_bays: c.psu_bays ?? 2, gpu_slots: c.gpu_slots ?? 0, max_tdp: c.max_tdp ?? null, gpu_arch_default: c.gpu_arch_default ?? 'none', rear_slots: rs })
  editOpen.value = true
}

function addSlot() { form.rear_slots.push({ name: '', cap: 1 }) }
function removeSlot(i: number) { form.rear_slots.splice(i, 1) }
function resetSlots() { form.rear_slots = DEFAULT_REAR_SLOTS.map(s => ({ ...s })) }

async function save() {
  if (!editing.value) return
  // 校验：槽位名不空、不重；cap≥0
  const names = form.rear_slots.map(s => (s.name || '').trim()).filter(Boolean)
  if (names.length !== new Set(names).size) { message.warning('后面板槽位名重复'); return }
  if (form.psu_bays < 0 || form.gpu_slots < 0) { message.warning('数量不能为负'); return }
  const payload = {
    psu_bays: Number(form.psu_bays) || 0,
    gpu_slots: Number(form.gpu_slots) || 0,
    max_tdp: form.max_tdp == null ? null : Number(form.max_tdp) || null,
    gpu_arch_default: form.gpu_arch_default || 'none',
    rear_slots: form.rear_slots.filter(s => (s.name || '').trim()).map(s => ({ name: s.name.trim(), cap: Number(s.cap) || 0 })),
  }
  saving.value = true
  try {
    await baseConfigApi.update(editing.value.id, payload)
    message.success('机箱能力已保存')
    editOpen.value = false
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

function resetAll() {
  Modal.confirm({
    title: '重置全部机箱能力为默认？',
    content: '把所有 base_config 的 rear_slots 还原成标准 2U 布局(IO1~4 各3 + OCP 1)、psu_bays=2、gpu_slots=0。不含已删行。',
    okText: '重置', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      for (const c of configs.value) {
        await baseConfigApi.update(c.id, { psu_bays: 2, gpu_slots: 0, max_tdp: null, gpu_arch_default: 'none', rear_slots: DEFAULT_REAR_SLOTS.map(s => ({ ...s })) })
      }
      message.success('已重置')
      await load()
    },
  })
}
</script>

<template>
  <div class="cce">
    <div class="cce-bar">
      <span class="cce-hint">机箱物理能力档案：电源槽 / 后面板槽位布局 / GPU 槽上限 / TDP 上限——决定配置时的容量边界与默认值。</span>
      <a-button size="small" @click="resetAll">重置为默认</a-button>
    </div>

    <a-spin :spinning="loading">
      <div class="cce-grid">
        <div v-for="c in configs" :key="c.id" class="cce-card glass-light">
          <div class="cce-card-head">
            <span class="cce-series">{{ c.series || '—' }} · {{ c.form || '—' }}</span>
            <a-button type="link" size="small" @click="openEdit(c)">编辑</a-button>
          </div>
          <div class="cce-name">{{ c.name }}</div>
          <div class="cce-meta">
            <div class="cce-meta-row"><span>电源槽</span><b>{{ c.psu_bays ?? 2 }}</b></div>
            <div class="cce-meta-row"><span>GPU 上限</span><b>{{ c.gpu_slots ?? 0 }}</b></div>
            <div class="cce-meta-row"><span>TDP 上限</span><b>{{ c.max_tdp ?? '—' }}<small v-if="c.max_tdp"> W</small></b></div>
            <div class="cce-meta-row"><span>GPU 架构</span><b>{{ gpuArchLabel(c.gpu_arch_default) }}</b></div>
          </div>
          <div class="cce-slots"><span class="cce-slots-lab">后面板</span><span class="cce-slots-val">{{ rearSummary(c.rear_slots) }}</span></div>
        </div>
        <div v-if="!loading && !configs.length" class="cce-empty">暂无基准配置</div>
      </div>
    </a-spin>

    <a-modal
      :open="editOpen"
      :title="`编辑机箱能力 · ${editing?.name || ''}`"
      :width="620"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      :mask-closable="false"
      @ok="save"
      @cancel="editOpen = false"
    >
      <div class="cce-form-row">
        <div class="cce-field">
          <label>电源槽位数 (psu_bays)</label>
          <a-input-number v-model:value="form.psu_bays" :min="0" :max="8" style="width:100%" />
        </div>
        <div class="cce-field">
          <label>GPU 槽上限 (gpu_slots)</label>
          <a-input-number v-model:value="form.gpu_slots" :min="0" :max="16" style="width:100%" />
        </div>
        <div class="cce-field">
          <label>TDP 上限 W (可空)</label>
          <a-input-number v-model:value="form.max_tdp" :min="0" placeholder="如 1200" style="width:100%" />
        </div>
        <div class="cce-field">
          <label>GPU 架构 (gpu_arch_default)</label>
          <a-select v-model:value="form.gpu_arch_default" :options="GPU_ARCH_OPTIONS" style="width:100%" />
        </div>
      </div>

      <div class="cce-slots-editor">
        <div class="cce-slots-head">
          <span>后面板槽位布局 (rear_slots)</span>
          <a-space :size="6">
            <a-button size="small" @click="addSlot">+ 槽位</a-button>
            <a-button size="small" type="link" @click="resetSlots">恢复标准布局</a-button>
          </a-space>
        </div>
        <div v-for="(s, i) in form.rear_slots" :key="i" class="cce-slot-row">
          <a-input v-model:value="s.name" placeholder="槽位名 (如 IO1 / OCP)" style="flex:1" />
          <a-input-number v-model:value="s.cap" :min="0" :max="12" placeholder="容量" style="width:110px">
            <template #addonBefore>容量</template>
          </a-input-number>
          <a-button danger size="small" @click="removeSlot(i)">删</a-button>
        </div>
        <div class="cce-slots-tip">容量 = 该槽可装的卡数（如 IO1=3 表示最多 3 张 Riser；OCP=1 单卡）。组合槽的「首次默认 1」由 chassisMeta.COMBO_REAR_SLOTS 控制。</div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.cce { padding: 4px 0; }
.cce-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.cce-hint { font-size: 12.5px; color: var(--cpq-text-muted); }
.cce-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.cce-card { border: 1px solid var(--cpq-glass-border); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }
.cce-card-head { display: flex; align-items: center; justify-content: space-between; }
.cce-series { font-size: 11.5px; color: var(--cpq-text-muted); letter-spacing: .3px; }
.cce-name { font-size: 14px; font-weight: 600; color: var(--cpq-text-primary); line-height: 1.35; }
.cce-meta { display: flex; gap: 16px; }
.cce-meta-row { display: flex; flex-direction: column; gap: 2px; }
.cce-meta-row span { font-size: 11px; color: var(--cpq-text-disabled); }
.cce-meta-row b { font-size: 15px; color: var(--cpq-text-primary); font-weight: 600; }
.cce-meta-row small { font-size: 10px; color: var(--cpq-text-muted); font-weight: 400; }
.cce-slots { display: flex; gap: 8px; align-items: baseline; padding-top: 6px; border-top: 1px solid var(--cpq-border-secondary); }
.cce-slots-lab { font-size: 11px; color: var(--cpq-text-muted); white-space: nowrap; }
.cce-slots-val { font-size: 12.5px; color: var(--cpq-text-secondary); }
.cce-empty { grid-column: 1/-1; text-align: center; color: var(--cpq-text-muted); padding: 40px 0; }
.cce-form-row { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 16px; }
.cce-field { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.cce-field label { font-size: 12px; color: var(--cpq-text-secondary); }
.cce-slots-editor { border-top: 1px solid var(--cpq-border-secondary); padding-top: 12px; }
.cce-slots-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-size: 13px; color: var(--cpq-text-primary); font-weight: 500; }
.cce-slot-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.cce-slots-tip { font-size: 11.5px; color: var(--cpq-text-muted); margin-top: 4px; line-height: 1.5; }
</style>
