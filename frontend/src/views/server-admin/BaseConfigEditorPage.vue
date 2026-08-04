<script setup lang="ts">
/** 基准配置全页双面板编辑器：左编辑（基础信息 + 料件拖拽清单）/ 右摘要（料件数 / 合计 / 功耗）。 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import { baseConfigApi, partsApi, bomTemplateApi, type BomTemplate, type PartMaster } from '@/api/serverConfig'
import { systemConfigApi, type OptionItem } from '@/api/systemConfig'
import { useSeriesStore } from '@/stores/series'
import PartPicker from '@/components/common/PartPicker.vue'
import { fromPartMaster } from '@/composables/usePartAdapter'
import { DEFAULT_REAR_SLOTS, GPU_ARCH_OPTIONS, rearSlotsFor } from '@/constants/chassisMeta'

const route = useRoute()
const router = useRouter()
const ALL_CAT = '全部'

const editingId = ref<number | null>(null)
const saving = ref(false)
const loading = ref(false)
const form = ref<any>({
  name: '', series: '', form: '2U', bays: 12, bom_template_id: null,
  // 机箱能力档案（原独立「机箱能力」编辑器，现并入：物理边界，决定配置容量与默认）
  psu_bays: 2, gpu_slots: 0, max_tdp: null as number | null, gpu_arch_default: 'none',
  rear_slots: DEFAULT_REAR_SLOTS.map(s => ({ ...s })),
  // config_content（riser / 内存速率等，数据驱动；description/spec_diff 由机型编辑维护）
  configContent: {
    description: '', spec_diff: '',
    standard_riser: {} as Record<string, string>,
    riser_x16: '', standard_mem_speed: null as number | null,
  },
})
interface Line { uid: number; cat: string; pn: string; qty: number }
const commonLines = ref<Line[]>([])
const allParts = ref<PartMaster[]>([])
const chassisCats = ref<string[]>([])
const templates = ref<BomTemplate[]>([])
const seriesStore = useSeriesStore()
const seriesOptions = seriesStore.items  // 全平台系列权威源（system_config.server_series）
const formOptions = ref<OptionItem[]>([{ value: '2U', label: '2U' }, { value: '4U', label: '4U' }])
let uidSeq = 1

function partsOf(cat: string) { return cat === ALL_CAT ? allParts.value : allParts.value.filter(p => p.category === cat) }
function partByPn(pn?: string) { return allParts.value.find(p => p.pn === pn) }

async function loadOptions() {
  seriesStore.ensureSeries()  // 系列走权威源 store（全平台）
  try {
    const f = await systemConfigApi.getValue<OptionItem[]>('server_form_factor')
    if (Array.isArray(f) && f.length) formOptions.value = f
  } catch { /* 降级默认 */ }
}

async function init() {
  loading.value = true
  try {
    const [partsRes, catsRes, tplRes] = await Promise.all([partsApi.list(), partsApi.categories(), bomTemplateApi.list()])
    allParts.value = partsRes.parts
    chassisCats.value = catsRes.categories
    templates.value = tplRes.templates || []
    const id = route.params.id as string | undefined
    if (id && id !== 'new') {
      editingId.value = Number(id)
      const full: any = await baseConfigApi.get(editingId.value)
      form.value = {
        name: full.name, series: full.series || '', form: full.form || '2U', bays: full.bays ?? 12, bom_template_id: full.bom_template_id ?? null,
        // 机箱能力档案（full 来自 baseConfigApi.get，含 psu_bays/rear_slots/gpu_slots/max_tdp/gpu_arch_default）
        psu_bays: full.psu_bays ?? 2, gpu_slots: full.gpu_slots ?? 0,
        max_tdp: full.max_tdp ?? null, gpu_arch_default: full.gpu_arch_default ?? 'none',
        rear_slots: (full.rear_slots?.length ? full.rear_slots : DEFAULT_REAR_SLOTS).map((s: any) => ({ name: s.name, cap: s.cap })),
      }
      commonLines.value = (full.parts || []).map((p: any) => ({ uid: uidSeq++, cat: p.category || ALL_CAT, pn: p.pn, qty: p.quantity }))
      // config_content：riser 按槽位展开（字符串=全槽同规格）、内存速率、保留 description/spec_diff
      const cc = full.config_content || {}
      const stdRiser: Record<string, string> = {}
      if (typeof cc.standard_riser === 'string') {
        ;(full.rear_slots || []).filter((s: any) => /^io/i.test((s.name || '').trim())).forEach((s: any) => { stdRiser[s.name] = cc.standard_riser as string })
      } else if (cc.standard_riser && typeof cc.standard_riser === 'object') {
        Object.assign(stdRiser, cc.standard_riser)
      }
      form.value.configContent = {
        description: cc.description || '', spec_diff: cc.spec_diff || '',
        standard_riser: stdRiser,
        riser_x16: cc.riser_x16 || '',
        standard_mem_speed: cc.standard_mem_speed != null && cc.standard_mem_speed !== '' ? Number(cc.standard_mem_speed) : null,
      }
    }
  } finally { loading.value = false }
}

function addLine() { commonLines.value.push({ uid: uidSeq++, cat: ALL_CAT, pn: '', qty: 1 }) }
function delLine(i: number) { commonLines.value.splice(i, 1) }
function onCatChange(i: number) {
  const l = commonLines.value[i]
  if (l.cat !== ALL_CAT && l.pn && !partsOf(l.cat).some(p => p.pn === l.pn)) l.pn = ''
}
function onPartPick(i: number, pn: string) {
  const l = commonLines.value[i]
  l.pn = pn
  const p = partByPn(pn)
  if (p) l.cat = p.category
}

// ---- 摘要 ----
const summary = computed(() => {
  let count = 0, price = 0, tdp = 0
  for (const l of commonLines.value) {
    if (!l.pn) continue
    const p = partByPn(l.pn)
    const q = Number(l.qty) || 0
    count += q
    if (p?.unit_price) price += p.unit_price * q
    const t = Number(p?.specs?.tdp) || Number(p?.specs?.power) || 0
    tdp += t * q
  }
  return { count, price, tdp }
})

// ---- 后面板槽位行（rear_slots 可增删，命名/容量可编辑）----
function addSlot() { form.value.rear_slots.push({ name: '', cap: 1 }) }
function removeSlot(i: number | string) { form.value.rear_slots.splice(Number(i), 1) }
function resetSlots() { form.value.rear_slots = rearSlotsFor(form.value.form, form.value.series) }
/** IO 槽判断（riser 规格按槽位配；OCP 是网卡位不算 riser） */
function isIoSlot(name?: string) { return /^io/i.test((name || '').trim()) }

async function save() {
  if (!form.value.name) return message.warning('请填基准名称')
  const parts = commonLines.value.filter(l => l.pn)
  if (!parts.length) return message.warning('请至少添加一个底盘件')
  // 槽位名校验：不重；数量非负
  const slotNames = form.value.rear_slots.map((s: any) => (s.name || '').trim()).filter(Boolean)
  if (slotNames.length !== new Set(slotNames).size) return message.warning('后面板槽位名重复')
  saving.value = true
  try {
    const payload: any = {
      name: form.value.name, series: form.value.series, model: form.value.name,
      form: form.value.form, bays: form.value.bays, bom_template_id: form.value.bom_template_id ?? null,
      // 机箱能力档案（原 ChassisCapabilityEditor 编辑的字段，现并入；修掉历史 gpu_arch_default 写死 'none' 的 clobber 坑）
      psu_bays: Number(form.value.psu_bays) || 0,
      gpu_slots: Number(form.value.gpu_slots) || 0,
      max_tdp: form.value.max_tdp == null ? null : (Number(form.value.max_tdp) || null),
      gpu_arch_default: form.value.gpu_arch_default || 'none',
      rear_slots: (form.value.rear_slots || []).filter((s: any) => (s.name || '').trim()).map((s: any) => ({ name: s.name.trim(), cap: Number(s.cap) || 0 })),
      // config_content：只写非空字段；standard_riser 按槽位 dict（留空的槽不落库 → 手填）
      config_content: (() => {
        const c: any = {}
        const d = form.value.configContent || {}
        if (d.description) c.description = d.description
        if (d.spec_diff) c.spec_diff = d.spec_diff
        const ioNames = new Set((form.value.rear_slots || []).map((s: any) => (s.name || '').trim()).filter((n: string) => /^io/i.test(n)))
        const stdRiser: Record<string, string> = {}
        for (const [k, v] of Object.entries(d.standard_riser || {})) {
          if (v && String(v).trim() && ioNames.has(k)) stdRiser[k] = String(v).trim()
        }
        if (Object.keys(stdRiser).length) c.standard_riser = stdRiser
        if (d.riser_x16 && String(d.riser_x16).trim()) c.riser_x16 = String(d.riser_x16).trim()
        if (d.standard_mem_speed != null && d.standard_mem_speed !== '') c.standard_mem_speed = Number(d.standard_mem_speed)
        return Object.keys(c).length ? c : null
      })(),
    }
    let id = editingId.value
    if (id) await baseConfigApi.update(id, payload)
    else id = (await baseConfigApi.create(payload)).id
    await baseConfigApi.setParts(id!, parts.map((l, idx) => ({ pn: l.pn, quantity: l.qty, sort_order: idx })))
    message.success((editingId.value ? '已更新' : '已新建') + '基准配置「' + form.value.name + '」')
    router.push({ path: '/servers/admin', query: { refresh: 'base-config' } })
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
function cancel() { router.push('/servers/admin') }

onMounted(async () => { await Promise.all([init(), loadOptions()]) })
</script>

<template>
  <div class="editor-page">
    <div class="content-inner">
      <div class="cfg-bar glass">
        <div class="cfg-bar-left">
          <a-button class="btn-ghost" @click="cancel">← 返回列表</a-button>
          <h2 class="cfg-title">{{ editingId ? '编辑基准配置' : '新建基准配置' }}</h2>
        </div>
        <div class="cfg-bar-right">
          <a-button @click="cancel">取消</a-button>
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
        </div>
      </div>

      <div class="two-col">
        <div class="col-left glass">
          <a-form layout="vertical" :disabled="loading">
            <a-row :gutter="12">
              <a-col :span="10"><a-form-item label="基准名称" required><a-input v-model:value="form.name" placeholder="如 Orion-2U-标准型" /></a-form-item></a-col>
              <a-col :span="5"><a-form-item label="系列"><a-select v-model:value="form.series"><a-select-option v-for="o in seriesOptions" :key="o.value" :value="o.value">{{ o.label }}</a-select-option></a-select></a-form-item></a-col>
              <a-col :span="4"><a-form-item label="形态"><a-select v-model:value="form.form"><a-select-option v-for="o in formOptions" :key="o.value" :value="o.value">{{ o.label }}</a-select-option></a-select></a-form-item></a-col>
              <a-col :span="5"><a-form-item label="盘位"><a-input-number v-model:value="form.bays" :min="1" style="width:100%" /></a-form-item></a-col>
            </a-row>
            <a-form-item label="BOM 模板">
              <a-select v-model:value="form.bom_template_id" allow-clear placeholder="(可选 — 报价时按模板推导)">
                <a-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}（{{ t.rows?.length || 0 }}行）</a-select-option>
              </a-select>
            </a-form-item>

            <div class="sec-label">机箱能力（物理边界 · 决定配置容量与默认值）</div>
            <a-row :gutter="12">
              <a-col :span="6"><a-form-item label="电源槽位"><a-input-number v-model:value="form.psu_bays" :min="0" :max="8" style="width:100%" /></a-form-item></a-col>
              <a-col :span="6"><a-form-item label="GPU 槽上限"><a-input-number v-model:value="form.gpu_slots" :min="0" :max="16" style="width:100%" /></a-form-item></a-col>
              <a-col :span="6"><a-form-item label="TDP 上限 (W)"><a-input-number v-model:value="form.max_tdp" :min="0" placeholder="可空" style="width:100%" /></a-form-item></a-col>
              <a-col :span="6"><a-form-item label="GPU 架构"><a-select v-model:value="form.gpu_arch_default" :options="GPU_ARCH_OPTIONS" /></a-form-item></a-col>
            </a-row>
            <div class="slot-editor">
              <div class="rear-edit-head">
                <span class="sec-label" style="margin:0">后面板槽位（每槽一张卡：数量 = 可装卡数；IO 槽可填 riser 预填规格）</span>
                <a-space :size="6">
                  <a-button size="small" @click="addSlot">+ 槽位</a-button>
                  <a-button size="small" type="link" @click="resetSlots">恢复标准布局</a-button>
                </a-space>
              </div>
              <div style="font-size:12px;color:var(--cpq-text-muted);margin:4px 0 8px">
                GPU 槽走上方「GPU 槽上限」(gpu_slots)；NVMe 模组作为槽内选项(option_type=nvme)。
                riser 填充优先级：装 GPU → 全 IO 槽取「升级规格」；100G/200G/400G 网卡 → IO1 取「升级规格」；否则取本槽预填；预填空 = 手填。
              </div>
              <div class="slot-grid">
                <div v-for="(s, i) in form.rear_slots" :key="i" class="slot-card">
                  <div class="slot-card-head">
                    <a-input v-model:value="s.name" placeholder="槽位名 (IO1 / OCP)" style="flex:1" />
                    <a-button danger size="small" @click="removeSlot(i)">✕</a-button>
                  </div>
                  <a-form-item label="数量（可装卡数）" :style="{ marginBottom: 6 }">
                    <a-input-number v-model:value="s.cap" :min="0" :max="12" style="width:100%" />
                  </a-form-item>
                  <a-form-item v-if="isIoSlot(s.name)" label="riser 预填规格（留空=手填）" :style="{ marginBottom: 0 }">
                    <a-input v-model:value="form.configContent.standard_riser[s.name]" placeholder="如 1*X16+1*X8 FHFL" />
                  </a-form-item>
                </div>
              </div>
              <a-row :gutter="12" style="margin-top:6px">
                <a-col :span="12">
                  <a-form-item label="升级规格 riser_x16（GPU / 100G+ 网卡时使用）">
                    <a-input v-model:value="form.configContent.riser_x16" placeholder="如 1*X16+1*X8 FHFL" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="标准内存速率 (MT/s)">
                    <a-input-number v-model:value="form.configContent.standard_mem_speed" :min="0" placeholder="如 4800" style="width:100%" />
                    <div style="font-size:12px;color:var(--cpq-text-muted)">需求未写速率时按此选件（技术员惯例 4800）</div>
                  </a-form-item>
                </a-col>
              </a-row>
            </div>
          </a-form>

          <div class="sec-label">底盘件（⣿ 拖拽排序；选中后自动归类）</div>
          <draggable v-model="commonLines" item-key="uid" handle=".drag-row" :animation="180" class="line-list">
            <template #item="{ element: l, index: i }">
              <div class="line-block">
                <div class="line-row">
                  <span class="drag-row" title="拖拽排序">⣿</span>
                  <span class="line-idx">{{ i + 1 }}</span>
                  <a-select v-model:value="l.cat" style="width:130px" @change="onCatChange(i)">
                    <a-select-option :value="ALL_CAT">🔍 全部</a-select-option>
                    <a-select-option v-for="c in chassisCats" :key="c" :value="c">{{ c }}</a-select-option>
                  </a-select>
                  <PartPicker style="flex:1" :items="partsOf(l.cat).map(fromPartMaster)" :model-value="l.pn" placeholder="🔍 搜索料号 / 名称 / PN…"
                              @update:model-value="(pn:any)=>onPartPick(i, typeof pn==='string'?pn:'')">
                    <template #option="{ item }">
                      <div class="bcb-opt">
                        <div class="bcb-opt-row"><span class="bcb-opt-name">{{ item.name }}</span><span v-if="item.unit_price != null" class="bcb-opt-price">¥{{ item.unit_price.toLocaleString() }}</span></div>
                        <div class="bcb-opt-sub"><span class="bcb-opt-cat">{{ item.category }}</span><span class="bcb-opt-pn">{{ item.pn }}</span></div>
                      </div>
                    </template>
                  </PartPicker>
                  <a-input-number v-model:value="l.qty" :min="1" style="width:72px" />
                  <a-button danger size="small" @click="delLine(i)">✕</a-button>
                </div>
                <div class="line-info" v-if="partByPn(l.pn)">
                  <span class="li-desc">{{ partByPn(l.pn)?.spec_text || '（无规格）' }}</span>
                  <span class="li-price">¥{{ (partByPn(l.pn)?.unit_price ?? 0).toLocaleString() }}</span>
                </div>
              </div>
            </template>
          </draggable>
          <a-button dashed style="margin-top:6px" @click="addLine">+ 添加底盘件</a-button>
        </div>

        <div class="col-right">
          <div class="glass summary-card">
            <div class="sum-row"><span>料件数</span><b>{{ summary.count }}</b></div>
            <div class="sum-row"><span>合计</span><b class="sum-price">¥{{ summary.price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</b></div>
            <div class="sum-row"><span>估算功耗</span><b>{{ summary.tdp }} W</b></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-page { min-height: 100vh; }
.content-inner { width: 100%; margin: 0 auto; padding: 24px; }
.cfg-bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; margin-bottom: 16px; }
.cfg-bar-left { display: flex; align-items: center; gap: 16px; }
.cfg-title { margin: 0; font-size: 16px; }
.cfg-bar-right { display: flex; gap: 8px; }
.btn-ghost { background: transparent; border: 1px solid var(--cpq-overlay-w15); }
.two-col { display: flex; gap: 16px; align-items: flex-start; }
.col-left { flex: 1; min-width: 0; padding: 16px; }
.col-right { flex: 0 0 240px; position: sticky; top: 16px; }
.sec-label { font-size: 13px; color: var(--cpq-text-muted, #6E7582); margin: 8px 0; }
.slot-editor { margin-bottom: 8px; }
.rear-edit-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.slot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
.slot-card { border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; padding: 10px 12px; background: var(--cpq-overlay-w4); }
.slot-card-head { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.line-list { min-height: 40px; }
.line-block { margin-bottom: 10px; }
.line-row { display: flex; gap: 6px; align-items: center; }
.drag-row { cursor: grab; color: var(--cpq-text-muted, #6E7582); padding: 0 4px; user-select: none; font-size: 16px; line-height: 1; }
.drag-row:active { cursor: grabbing; }
.line-idx { font-size: 11px; color: var(--cpq-text-muted, #6E7582); font-variant-numeric: tabular-nums; width: 18px; text-align: center; flex-shrink: 0; }
.line-info { display: flex; justify-content: space-between; gap: 12px; padding: 4px 4px 0; margin-top: 2px; font-size: 13px; }
.li-desc { color: var(--cpq-text-secondary, #9BA1AA); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.li-price { color: var(--cpq-accent-primary); font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.summary-card { padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.sum-row { display: flex; justify-content: space-between; align-items: baseline; font-size: 13px; }
.sum-row span { color: var(--cpq-text-muted, #6E7582); }
.sum-row b { font-variant-numeric: tabular-nums; }
.sum-price { color: var(--cpq-accent-primary); font-size: 16px; }
</style>

<!-- PartPicker 下拉 teleported 到 body，非 scoped；用 .bcb-opt 前缀限定 -->
<style>
.bcb-opt { padding: 5px 2px; line-height: 1.45; }
.bcb-opt-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.bcb-opt-name { font-size: 14px; color: var(--cpq-text-primary, #E8ECEF); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bcb-opt-price { font-size: 13px; color: var(--cpq-accent-primary); font-weight: 600; white-space: nowrap; }
.bcb-opt-sub { display: flex; gap: 8px; align-items: center; margin-top: 2px; font-size: 12px; }
.bcb-opt-cat { color: var(--cpq-accent-primary); }
.bcb-opt-pn { color: var(--cpq-text-muted, #6E7582); margin-left: auto; font-family: monospace; }
</style>
