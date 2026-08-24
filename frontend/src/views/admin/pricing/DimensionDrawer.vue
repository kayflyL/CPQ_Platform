<script setup lang="ts">
/** 定价维度配置抽屉 —— 按 dimKey 渲染系数表编辑器，保存 create/update strategy。
 *  platform_baseline/industry_adj/order_mult/form_adj/part_margin：枚举→数值表；
 *  region_adj：分桶因子(±百分点+每台固定费) + 分桶关键词；cost_tier：阶梯行；guardrail：保底封顶双值+订单类型分档。
 *  未持久化的维度（strategyId=null）保存时 create，已有则 update。 */
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { strategyApi } from '@/api/strategies'
import {
  DIMENSION_MAP, PLATFORM_OPTIONS, INDUSTRY_OPTIONS, CUSTOMER_TYPE_OPTIONS, REGION_BUCKET_OPTIONS, FORM_OPTIONS,
  PART_CATEGORY_OPTIONS, PART_MARGIN_META,
  type DrawerDimKey,
} from '@/constants/pricingMeta'

const props = defineProps<{
  open: boolean
  dimKey: DrawerDimKey | null
  initialBody: any
  strategyId: number | null
}>()
const emit = defineEmits<{ 'update:open': [boolean]; saved: [] }>()

const saving = ref(false)
const def = computed(() => {
  if (!props.dimKey) return null
  if (props.dimKey === 'part_margin') {
    // 非流水线的分项毛利（deal 目标之上的品类修正），复用本抽屉的枚举表编辑
    return { label: PART_MARGIN_META.label, desc: PART_MARGIN_META.desc, opKind: 'add', sign: '+', unit: '百分点', shortLabel: PART_MARGIN_META.shortLabel }
  }
  return DIMENSION_MAP[props.dimKey]
})

// ── 枚举→数值表（platform_baseline / industry_adj / order_mult / form_adj / part_margin）──
const coeffRows = ref<Array<{ key: string; value: number | null }>>([])
// region：三桶 ±百分点 + 每台固定费（海外报关/物流）
const factors = ref<Record<string, { pct: number | null; fee: number | null }>>({
  国内: { pct: 0, fee: 0 }, 海外: { pct: 0, fee: 0 }, 偏远: { pct: 0, fee: 0 },
})
const kwOverseas = ref<string[]>([])
const kwRemote = ref<string[]>([])
// cost_tier
const tierRows = ref<Array<{ max: number | null; mult: number | null }>>([])
// qty_mult
const qtyBands = ref<Array<{ min: number | null; mult: number | null }>>([])
// guardrail：默认档 + 按订单类型分档
const floor = ref<number | null>(7)
const cap = ref<number | null>(30)
const grTiers = ref<Array<{ customer_type: string; floor: number | null; cap: number | null }>>([])

const ENUM_TABLE_KEYS = ['platform_baseline', 'industry_adj', 'order_mult', 'form_adj', 'part_margin']

/** 各枚举维度的下拉选项 + 数值约束（非枚举表维度必须返回 null，否则模板首个 v-if 枚举表分支会遮蔽 region/cost_tier/qty_mult/guardrail 专门分支）*/
const enumConfig = computed(() => {
  if (!props.dimKey || !ENUM_TABLE_KEYS.includes(props.dimKey)) return null
  const opts = props.dimKey === 'platform_baseline' ? PLATFORM_OPTIONS
    : props.dimKey === 'industry_adj' ? INDUSTRY_OPTIONS
      : props.dimKey === 'form_adj' ? FORM_OPTIONS
        : props.dimKey === 'part_margin' ? PART_CATEGORY_OPTIONS
          : CUSTOMER_TYPE_OPTIONS
  if (props.dimKey === 'platform_baseline') return { opts, min: 0, max: 60, step: 1, unit: '%' }
  if (props.dimKey === 'industry_adj' || props.dimKey === 'form_adj' || props.dimKey === 'part_margin') {
    return { opts, min: -30, max: 30, step: 1, unit: '百分点' }
  }
  return { opts, min: 0, max: 3, step: 0.05, unit: '×' } // order_mult
})

watch(() => props.open, (v) => {
  if (!v || !props.dimKey) return
  const b = props.initialBody || {}
  if (ENUM_TABLE_KEYS.includes(props.dimKey)) {
    const known = (enumConfig.value?.opts || []).map(o => o.value)
    const rows: Array<{ key: string; value: number | null }> = known.map(k => ({ key: k, value: b[k] != null ? Number(b[k]) : null }))
    // body 里有但不在已知枚举里的（自定义）
    for (const k of Object.keys(b || {})) if (!known.includes(k)) rows.push({ key: k, value: Number(b[k]) })
    coeffRows.value = rows
  } else if (props.dimKey === 'region_adj') {
    const f = b.factors || {}
    const norm = (v: any) => (typeof v === 'object' && v != null
      ? { pct: Number.isFinite(Number(v.pct)) ? Number(v.pct) : 0, fee: Number.isFinite(Number(v.fixed_fee)) ? Number(v.fixed_fee) : 0 }
      : { pct: Number.isFinite(Number(v)) ? Number(v) : 0, fee: 0 })
    factors.value = { 国内: norm(f['国内']), 海外: norm(f['海外']), 偏远: norm(f['偏远']) }
    const kw = b.keywords || {}
    kwOverseas.value = Array.isArray(kw['海外']) ? kw['海外'] : []
    kwRemote.value = Array.isArray(kw['偏远']) ? kw['偏远'] : []
  } else if (props.dimKey === 'cost_tier') {
    tierRows.value = Array.isArray(b.tiers) ? b.tiers.map((t: any) => ({ max: t.max != null ? Number(t.max) : null, mult: t.mult != null ? Number(t.mult) : null }))
      : [{ max: null, mult: null }]
  } else if (props.dimKey === 'qty_mult') {
    qtyBands.value = Array.isArray(b.bands) ? b.bands.map((x: any) => ({ min: x.min != null ? Number(x.min) : null, mult: x.mult != null ? Number(x.mult) : null }))
      : [{ min: 1, mult: 1 }]
  } else if (props.dimKey === 'guardrail') {
    floor.value = b.floor != null ? Number(b.floor) : 7
    cap.value = b.cap != null ? Number(b.cap) : 30
    grTiers.value = Array.isArray(b.tiers)
      ? b.tiers.filter((t: any) => t && t.customer_type).map((t: any) => ({
          customer_type: String(t.customer_type), floor: Number.isFinite(Number(t.floor)) ? Number(t.floor) : null, cap: Number.isFinite(Number(t.cap)) ? Number(t.cap) : null,
        }))
      : []
  }
})

function addCoeffRow() { coeffRows.value.push({ key: '', value: null }) }
function removeCoeffRow(i: number) { coeffRows.value.splice(i, 1) }
function addTierRow() { tierRows.value.push({ max: null, mult: null }) }
function removeTierRow(i: number) { tierRows.value.splice(i, 1) }
function addQtyBand() { qtyBands.value.push({ min: null, mult: null }) }
function removeQtyBand(i: number) { qtyBands.value.splice(i, 1) }
function addGrTier() { grTiers.value.push({ customer_type: '', floor: null, cap: null }) }
function removeGrTier(i: number) { grTiers.value.splice(i, 1) }

function buildBody(): any {
  const k = props.dimKey
  if (!k) return null
  if (ENUM_TABLE_KEYS.includes(k)) {
    const out: Record<string, number> = {}
    for (const r of coeffRows.value) {
      const key = String(r.key || '').trim()
      if (key && r.value != null && Number.isFinite(r.value)) out[key] = Number(r.value)
    }
    return out
  }
  if (k === 'region_adj') {
    const out: Record<string, number | { pct: number; fixed_fee: number }> = {}
    for (const bucket of Object.keys(factors.value)) {
      const p = Number(factors.value[bucket].pct) || 0
      const f = Number(factors.value[bucket].fee) || 0
      out[bucket] = f > 0 ? { pct: p, fixed_fee: f } : p   // 无固定费保持纯数字（兼容紧凑）
    }
    return { factors: out, keywords: { 海外: kwOverseas.value, 偏远: kwRemote.value } }
  }
  if (k === 'cost_tier') {
    return { tiers: tierRows.value.filter(t => t.mult != null).map(t => ({ ...(t.max != null ? { max: Number(t.max) } : {}), mult: Number(t.mult) })) }
  }
  if (k === 'qty_mult') {
    return { bands: qtyBands.value.filter(b => b.mult != null).map(b => ({ min: Number(b.min) || 1, mult: Number(b.mult) })).sort((a, b) => a.min - b.min) }
  }
  // guardrail：默认档 + 订单类型分档（非法行丢弃）
  const ts = grTiers.value
    .filter(t => String(t.customer_type || '').trim() && t.floor != null && t.cap != null && Number(t.floor) < Number(t.cap))
    .map(t => ({ customer_type: String(t.customer_type).trim(), floor: Number(t.floor), cap: Number(t.cap) }))
  return { floor: Number(floor.value) || 0, cap: Number(cap.value) || 0, ...(ts.length ? { tiers: ts } : {}) }
}

async function save() {
  if (!props.dimKey || !def.value) return
  const body = buildBody()
  // 轻量校验
  if (props.dimKey === 'guardrail' && Number(body.floor) >= Number(body.cap)) { message.warning('保底需小于封顶'); return }
  saving.value = true
  try {
    if (props.strategyId) {
      await strategyApi.update(props.strategyId, { body, name: def.value.label, description: def.value.desc })
    } else {
      await strategyApi.create({ domain: 'pricing', type: props.dimKey, name: def.value.label, scope: null, body, status: 'active', description: def.value.desc })
    }
    message.success('已保存（演算器即时生效）')
    emit('saved')
    emit('update:open', false)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <a-drawer :open="open" :title="def ? `配置维度 · ${def.label}` : '配置'" width="600"
            @close="$emit('update:open', false)" :footer-style="{ textAlign: 'right' }">
    <template #footer>
      <a-button style="margin-right: 8px" @click="$emit('update:open', false)">取消</a-button>
      <a-button type="primary" :loading="saving" @click="save">保存</a-button>
    </template>

    <a-alert v-if="def" :message="def.desc" type="info" show-icon style="margin-bottom: 16px" />
    <p v-if="def" class="pd-hint">运算类型：<b>{{ def.opKind }}</b>（{{ def.sign || '基准' }} {{ def.unit }}）。点保存即时生效，演算器与本计算同步。</p>

    <!-- 枚举→数值表 -->
    <a-form v-if="dimKey && enumConfig" layout="vertical">
      <div v-for="(r, i) in coeffRows" :key="i" class="pd-row">
        <a-input v-if="!enumConfig.opts.find(o => o.value === r.key)" v-model:value="r.key" placeholder="自定义键" style="width: 150px" />
        <span v-else class="pd-row-key">{{ enumConfig.opts.find(o => o.value === r.key)?.label || r.key }}</span>
        <a-input-number v-model:value="r.value" :min="enumConfig.min" :max="enumConfig.max" :step="enumConfig.step" style="flex:1">
          <template #addonAfter>{{ enumConfig.unit }}</template>
        </a-input-number>
        <a-button size="small" link danger @click="removeCoeffRow(i)">删</a-button>
      </div>
      <a-button size="small" type="dashed" @click="addCoeffRow" style="margin-top: 8px">+ 自定义键</a-button>
    </a-form>

    <!-- region_adj -->
    <a-form v-else-if="dimKey === 'region_adj'" layout="vertical">
      <a-divider orientation="left" class="pd-sec">分桶因子（±百分点 + 每台固定费）</a-divider>
      <div v-for="bk in REGION_BUCKET_OPTIONS" :key="bk.value" class="pd-row">
        <span class="pd-row-key">{{ bk.label }}</span>
        <a-input-number v-model:value="factors[bk.value].pct" :min="-30" :max="30" :step="1" style="flex:1">
          <template #addonAfter>百分点</template>
        </a-input-number>
        <a-input-number v-model:value="factors[bk.value].fee" :min="0" :step="100" placeholder="0=无" style="width: 170px">
          <template #addonAfter>费/台</template>
        </a-input-number>
      </div>
      <p class="pd-hint">固定费 = 每台附加金额（海外报关/国际物流/海外质保等），只进建议售价、不进毛利率；0 = 无。</p>
      <a-divider orientation="left" class="pd-sec">分桶关键词（命中即归该桶；偏远优先于海外）</a-divider>
      <a-form-item label="海外 关键词">
        <a-select v-model:value="kwOverseas" mode="tags" style="width:100%" :token-separators="[',']" placeholder="输入回车添加，如 东南亚、欧美" />
      </a-form-item>
      <a-form-item label="偏远 关键词">
        <a-select v-model:value="kwRemote" mode="tags" style="width:100%" :token-separators="[',']" placeholder="如 西藏、新疆" />
      </a-form-item>
      <p class="pd-hint">国内是默认兜底桶（无需关键词）。引擎按 delivery_region 文本命中关键词分桶。</p>
    </a-form>

    <!-- cost_tier -->
    <a-form v-else-if="dimKey === 'cost_tier'" layout="vertical">
      <p class="pd-hint">按整机 BOM 总成本落档，乘对应系数（成本越高点位越低）。成本 ≤ max 落该档；最后一条不填 max = 超出所有上限的兜底档。</p>
      <div v-for="(t, i) in tierRows" :key="i" class="pd-row">
        <a-input-number v-model:value="t.max" :min="0" :step="10000" placeholder="成本上限(元)，留空=兜底档" style="flex:1">
          <template #addonAfter>≤ 元</template>
        </a-input-number>
        <a-input-number v-model:value="t.mult" :min="0" :max="3" :step="0.05" placeholder="系数" style="width: 140px">
          <template #addonAfter>×</template>
        </a-input-number>
        <a-button size="small" link danger @click="removeTierRow(i)">删</a-button>
      </div>
      <a-button size="small" type="dashed" @click="addTierRow" style="margin-top: 8px">+ 加一档</a-button>
    </a-form>

    <!-- qty_mult -->
    <a-form v-else-if="dimKey === 'qty_mult'" layout="vertical">
      <p class="pd-hint">按销售台数分档乘系数（量越大让利越多）。台数 ≥ min 落该档；引擎取满足条件的最大档。建议 min 从小到大、系数从高到低。</p>
      <div v-for="(bd, i) in qtyBands" :key="i" class="pd-row">
        <a-input-number v-model:value="bd.min" :min="1" :step="1" placeholder="起步台数" style="flex:1">
          <template #addonAfter>≥ 台</template>
        </a-input-number>
        <a-input-number v-model:value="bd.mult" :min="0" :max="3" :step="0.05" placeholder="系数" style="width: 140px">
          <template #addonAfter>×</template>
        </a-input-number>
        <a-button size="small" link danger @click="removeQtyBand(i)">删</a-button>
      </div>
      <a-button size="small" type="dashed" @click="addQtyBand" style="margin-top: 8px">+ 加一档</a-button>
    </a-form>

    <!-- guardrail -->
    <a-form v-else-if="dimKey === 'guardrail'" layout="vertical">
      <p class="pd-hint">最终毛利率夹在 [保底, 封顶] 之间。低于保底上调、高于封顶下调。（工作台利润率告警已独立到「利润率告警」策略，不再读保底线。）</p>
      <div class="pd-row">
        <span class="pd-row-key">默认保底 floor</span>
        <a-input-number v-model:value="floor" :min="0" :max="80" :step="1" style="flex:1"><template #addonAfter>%</template></a-input-number>
      </div>
      <div class="pd-row">
        <span class="pd-row-key">默认封顶 cap</span>
        <a-input-number v-model:value="cap" :min="0" :max="100" :step="1" style="flex:1"><template #addonAfter>%</template></a-input-number>
      </div>
      <a-divider orientation="left" class="pd-sec">按订单类型分档红线（可选；首命中）</a-divider>
      <p class="pd-hint">差异化红线：不同客户类型可用不同 [保底, 封顶]（如渠道/集采毛利天然被系数压低，红线放宽）。deal 未命中分档走上面的默认档。</p>
      <div v-for="(t, i) in grTiers" :key="i" class="pd-row">
        <a-select v-model:value="t.customer_type" :options="CUSTOMER_TYPE_OPTIONS" placeholder="客户类型" style="width: 140px" />
        <a-input-number v-model:value="t.floor" :min="0" :max="80" :step="1" placeholder="保底" style="flex:1"><template #addonAfter>%</template></a-input-number>
        <a-input-number v-model:value="t.cap" :min="0" :max="100" :step="1" placeholder="封顶" style="flex:1"><template #addonAfter>%</template></a-input-number>
        <a-button size="small" link danger @click="removeGrTier(i)">删</a-button>
      </div>
      <a-button size="small" type="dashed" @click="addGrTier" style="margin-top: 8px">+ 加一档</a-button>
    </a-form>
  </a-drawer>
</template>

<style scoped>
.pd-hint { font-size: 12px; color: var(--cpq-text-muted); margin: 4px 0 12px; }
.pd-sec { font-size: 13px; margin-top: 8px; }
.pd-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.pd-row-key { width: 150px; font-size: 13px; color: var(--cpq-text-primary); flex: none; }
</style>
