<script setup lang="ts">
/** 配置规格书（服务器页产物）— 面向客户的 datasheet 风格文档。
 *  纯展示组件：数据来自父级（ConfigWizard 的 l6Apply / kpLines / kpPart / priceOf）+ 品牌（store）。
 *  刻意做成「白纸黑字」的文档卡片（不跟随 app 主题），浅/深色模式与打印输出一致。
 *  打印样式放非 scoped <style>（@media print 需跳出 scoped 边界，由 .spec-sheet-root 锚定）。 */
import { computed } from 'vue'
import type { ServerModel, KpPart } from '@/api/serverConfig'
import type { Branding } from '@/store/settings'
import { DEFAULT_COMMERCIAL_TERMS } from '@/store/settings'
import { DEFAULT_LABELS } from '@/types/specTemplate'
import type { DisplayOptions } from '@/types/specTemplate'

/** 多配置模式的数据结构 */
interface ConfigItem {
  config_name: string
  server_model: string
  quantity: number
  l6_details: L6Item[]
  kp_details: KpItem[]
  warranty_details?: WarrantyItem[]
  l6_total: number
  kp_total: number
  warranty_total?: number
  unit_price: number
  total_price: number
  // 机箱规格
  chassis_form?: string      // 机箱形态
  chassis_bays?: string      // 盘位
  chassis_series?: string    // 系列（Orion/Polaris）
  backplane_type?: string    // 背板类型（Tri-Mode/Pass-Thru）
  power_supply?: string      // 电源
  // 维保条款描述（来自 /api/system-config/warranty_desc_*）
  warranty_desc_l6?: string
  warranty_desc_kp?: string
}

interface L6Item {
  catalogue: string
  description: string
  part_category: string
  qty: number
  category: string
  final_price: number
}

interface KpItem {
  catalogue: string
  description: string
  part_category: string
  qty: number
  category: string
  final_price: number
}

interface WarrantyItem {
  catalogue: string
  description: string
  part_category: string
  qty: number
  category: string
  final_price: number
}

const props = defineProps<{
  /** 新接口：多配置模式 */
  configs?: ConfigItem[]
  branding: Branding
  businessPerson?: string
  displayOptions?: {
    show_price_column?: boolean
    show_chassis_total?: boolean
    show_kp_subtotal?: boolean
    show_config_subtotal?: boolean
    show_grand_total?: boolean
    show_footer_check?: boolean
    show_commercial_terms?: boolean
    labels?: DisplayOptions['labels']
  }
  /** 兼容旧接口 */
  legacyMode?: boolean
  model?: ServerModel
  l6Apply?: { totals?: any; l6Rows?: any[]; picks?: any } | null
  kpLines?: { cat: string; pn: string; qty: number }[]
  kpPart?: (pn: string) => KpPart | undefined
  priceOf?: (pn: string) => number
  series?: string
}>()

// 判断模式：有 configs prop 则走新模式（即使为空数组），否则走旧模式
const isLegacyMode = computed(() => {
  // 如果明确传入了 configs prop（即使是空数组），走新模式
  if (props.configs !== undefined) {
    console.log('[SpecSheet] 新模式，configs:', props.configs?.length, '条数据')
    return false
  }
  // 否则走旧模式
  console.log('[SpecSheet] 旧模式')
  return props.legacyMode || true
})

// 标签合并：用户自定义优先，否则用默认值
const labels = computed(() => ({
  ...DEFAULT_LABELS,
  ...props.displayOptions?.labels,
}))

// 默认全部显示
const opts = computed(() => ({
  show_price_column: props.displayOptions?.show_price_column !== false,
  show_chassis_total: props.displayOptions?.show_chassis_total !== false,
  show_kp_subtotal: props.displayOptions?.show_kp_subtotal !== false,
  show_config_subtotal: props.displayOptions?.show_config_subtotal !== false,
  show_grand_total: props.displayOptions?.show_grand_total !== false,
  show_footer_check: props.displayOptions?.show_footer_check !== false,
  show_commercial_terms: props.displayOptions?.show_commercial_terms !== false,
}))

// 报价条款：合并默认口径，只保留非空项（按 报价单位→有效期→交付付款→寄送 固定顺序）
const terms = computed<(readonly [string, string])[]>(() => {
  const t = { ...DEFAULT_COMMERCIAL_TERMS, ...(props.branding?.commercial_terms || {}) }
  const ordered: Array<[string, string]> = [
    ['报价单位', t.currency || ''],
    ['有效期', t.validity || ''],
    ['交付/付款', t.delivery || ''],
    ['寄送', t.shipping || ''],
  ]
  return ordered.filter(([, v]) => v && v.trim())
})

const docDate = new Date().toLocaleDateString('zh-CN')

// ==================== 旧模式计算属性 ====================
const hasChassis = computed(() => !!props.l6Apply)
const chassisTotal = computed(() => Number(props.l6Apply?.totals?.l6) || 0)

// 机箱摘要 5 项
const bpTypeLabel = computed(() => {
  const rows = props.l6Apply?.l6Rows || []
  const byRe = (re: RegExp) => rows.find((r: any) => re.test(String(r.catalogue || '')))
  const bpRow = byRe(/背板/) || byRe(/backplane/i)
  if (bpRow?.catalogue) return String(bpRow.catalogue)
  return props.l6Apply?.picks?.bp_type || ''
})
const powerDesc = computed(() => {
  const rows = props.l6Apply?.l6Rows || []
  const psu = rows.find((r: any) => typeof r.catalogue === 'string' && r.catalogue.startsWith('电源:'))
  if (!psu) return ''
  const name = String(psu.catalogue).replace(/^电源:/, '').trim()
  return `${psu.qty ?? 1} × ${name || '电源'}`
})

const kpTotal = computed(() =>
  (props.kpLines || []).reduce((s, l) => s + ((props.priceOf?.(l.pn) || 0) * (l.qty || 0)), 0)
)
const grand = computed(() => chassisTotal.value + kpTotal.value)

// KP 按 cat 分组，保留首次出现顺序
const kpGroups = computed(() => {
  const map: Record<string, { cat: string; pn: string; qty: number }[]> = {}
  const order: string[] = []
  for (const l of (props.kpLines || [])) {
    if (!map[l.cat]) { map[l.cat] = []; order.push(l.cat) }
    map[l.cat].push(l)
  }
  return order.map(cat => ({ cat, lines: map[cat] }))
})

const subtitle = computed(() => {
  if (!props.model) return ''
  const bc = props.model.base_config
  return [bc?.form, props.model.use, bc?.bays ? `${bc.bays} 盘位` : '']
    .filter(Boolean).join(' · ')
})

// ==================== 新模式计算属性 ====================
const activeConfigs = computed(() => props.configs || [])

// 工具函数
function money(n: number | string | null | undefined): string {
  if (n == null || n === '' || isNaN(Number(n))) return '—'
  const num = Number(n)
  if (num <= 0) return '—'
  return '¥' + num.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

function specDesc(part: KpPart | undefined): string {
  if (!part) return ''
  const s: any = (part as any).specs
  if (!s) return ''
  if (typeof s === 'string') return s
  const vals = Object.values(s).filter(v => v != null && v !== '').map(v => String(v))
  return vals.length ? vals.join(' · ') : ''
}

// Description = 料件名（+ specs，若有）。料号库 specs 多不全，靠 name 兜底保证永远有内容。
function descOf(part: KpPart | undefined): string {
  if (!part) return '—'
  const specsStr = specDesc(part)
  return [part.name, specsStr].filter(Boolean).join(specsStr ? ' · ' : '') || part.pn || '—'
}

// 新模式：从 kpItem 获取描述
// KpItem 已切到 catalogue/description/part_category（PreviewKpItem 契约）：catalogue=型号，description 通常空
function getKpDesc(item: KpItem): string {
  const specsStr = item.description || ''
  return [item.catalogue, specsStr].filter(Boolean).join(' · ') || '—'
}

// 新模式：KP 按分类分组（category 来自后端，通常等同 part_category）
function groupByCategory(items: KpItem[]) {
  const map: Record<string, KpItem[]> = {}
  const order: string[] = []
  for (const item of items) {
    const cat = item.part_category || item.category || 'Key Parts'
    if (!map[cat]) { map[cat] = []; order.push(cat) }
    map[cat].push(item)
  }
  return order.map(cat => ({ category: cat, items: map[cat] }))
}
</script>

<template>
  <div class="spec-sheet" :class="{ 'spec-sheet--multi': !isLegacyMode }">
    <!-- ==================== 兼容模式：旧逻辑 ==================== -->
    <template v-if="isLegacyMode">
      <!-- 抬头 -->
      <header class="ss-header">
        <div class="ss-brand">
          <img v-if="branding.logo_url" :src="branding.logo_url" class="ss-logo" alt="logo" />
          <div class="ss-brand-text">
            <div class="ss-company">{{ branding.company_name || '' }}</div>
            <div v-if="branding.tagline" class="ss-tagline">{{ branding.tagline }}</div>
          </div>
        </div>
        <div class="ss-doc">
          <div class="ss-doc-title">{{ branding.doc_title || '配置规格书 / Server Build Specification' }}</div>
          <div class="ss-doc-meta">日期 {{ docDate }}</div>
        </div>
      </header>

      <!-- 标题块 -->
      <section class="ss-title-block">
        <div class="ss-title-name">{{ model?.name || '—' }}</div>
        <div v-if="subtitle" class="ss-title-sub">{{ subtitle }}</div>
        <span v-if="series || model?.base_config?.form" class="ss-chip">{{ series || model?.base_config?.form }}</span>
      </section>

      <!-- 机箱规格：5 项摘要 + 总价 -->
      <section class="ss-section">
        <div class="ss-section-title">{{ labels.chassis_title }}</div>
        <div v-if="hasChassis" class="ss-spec-grid">
          <div class="spec-item"><span class="spec-key">{{ labels.chassis_model }}</span><span class="spec-val">{{ model?.name || '—' }}</span></div>
          <div class="spec-item"><span class="spec-key">{{ labels.chassis_form }}</span><span class="spec-val">{{ model?.base_config?.form || '—' }}</span></div>
          <div class="spec-item"><span class="spec-key">{{ labels.chassis_bays }}</span><span class="spec-val">{{ model?.base_config?.bays ? `${model.base_config.bays} 盘位` : '—' }}</span></div>
          <div class="spec-item"><span class="spec-key">{{ labels.chassis_backplane }}</span><span class="spec-val">{{ bpTypeLabel || '—' }}</span></div>
          <div class="spec-item"><span class="spec-key">{{ labels.chassis_power }}</span><span class="spec-val">{{ powerDesc || '—' }}</span></div>
          <div v-if="opts.show_chassis_total" class="spec-item spec-total">
            <span class="spec-key">{{ labels.chassis_total }}</span><span class="spec-val">{{ money(chassisTotal) }}</span>
          </div>
        </div>
        <div v-else class="ss-empty">请先完成机箱选配</div>
      </section>

      <!-- KP 配件 -->
      <section v-if="kpGroups.length" class="ss-section">
        <div class="ss-section-title">{{ labels.kp_title }} · Peripherals</div>
        <table class="ss-table">
          <thead>
            <tr>
              <th class="col-cat">{{ labels.kp_catalogue }}</th><th class="col-desc">{{ labels.kp_description }}</th>
              <th class="col-qty">{{ labels.kp_qty }}</th><th v-if="opts.show_price_column" class="col-cost">{{ labels.kp_cost }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in kpGroups" :key="g.cat">
              <tr v-for="(l, i) in g.lines" :key="g.cat + i" :class="{ 'group-first': i === 0 }">
                <td class="cell-cat">{{ g.cat }}</td>
                <td class="cell-desc">{{ descOf(kpPart?.(l.pn)) }}</td>
                <td class="cell-qty">{{ l.qty ?? '—' }}</td>
                <td v-if="opts.show_price_column" class="cell-cost">{{ money((priceOf?.(l.pn) || 0) * (l.qty || 0)) }}</td>
              </tr>
            </template>
            <tr v-if="opts.show_kp_subtotal" class="ss-subtotal">
              <td :colspan="opts.show_price_column ? 3 : 2">{{ labels.kp_subtotal }}</td>
              <td v-if="opts.show_price_column">{{ money(kpTotal) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 合计 -->
      <section v-if="opts.show_grand_total" class="ss-grand">
        <span class="ss-grand-label">{{ labels.grand_total }}</span>
        <span class="ss-grand-val">{{ money(grand) }}</span>
      </section>

      <!-- 报价条款 -->
      <section v-if="opts.show_commercial_terms && terms.length" class="ss-terms">
        <div class="ss-terms-title">报价条款 / Terms</div>
        <div class="ss-terms-grid">
          <div v-for="[label, text] in terms" :key="label" class="ss-terms-item">
            <span class="ss-terms-label">{{ label }}</span>
            <span class="ss-terms-text">{{ text }}</span>
          </div>
        </div>
      </section>

      <!-- 页脚 -->
      <footer class="ss-footer">
        <div v-if="opts.show_footer_check" class="ss-check">✓ 已通过机型兼容校验</div>
        <div class="ss-contact">
          <span v-if="branding.contact_phone">TEL {{ branding.contact_phone }}</span>
          <span v-if="branding.contact_email">EMAIL {{ branding.contact_email }}</span>
          <span v-if="branding.address">{{ branding.address }}</span>
        </div>
        <div v-if="branding.footer_note" class="ss-footnote">{{ branding.footer_note }}</div>
      </footer>
    </template>

    <!-- ==================== 多配置模式 ==================== -->
    <template v-else>
      <div v-if="!activeConfigs.length" class="ss-empty">
        请选择商机并点击"加载预览"按钮查看规格书预览
      </div>
      <!-- 配置循环：每配置单独一页 A4 -->
      <template v-for="cfg in activeConfigs" :key="cfg.config_name">
        <div class="ss-page">
          <!-- 抬头（每页重复：品牌信息） -->
          <header class="ss-header">
            <div class="ss-brand">
              <img v-if="branding.logo_url" :src="branding.logo_url" class="ss-logo" alt="logo" />
              <div class="ss-brand-text">
                <div class="ss-company">{{ branding.company_name || '' }}</div>
                <div v-if="branding.tagline" class="ss-tagline">{{ branding.tagline }}</div>
              </div>
            </div>
            <div class="ss-doc">
              <div class="ss-doc-title">{{ branding.doc_title || '配置规格书 / Server Build Specification' }}</div>
              <div class="ss-doc-meta">日期 {{ docDate }}</div>
            </div>
          </header>

          <!-- 配置标题块：服务器型号 + 系列chip -->
          <section class="ss-title-block ss-title-block--inline">
            <div class="ss-title-left">
              <div class="ss-title-name">{{ cfg.server_model || cfg.config_name }}</div>
              <span class="ss-chip">{{ cfg.chassis_series || '' }}</span>
            </div>
            <div class="ss-title-right">
              <span v-if="businessPerson" class="ss-to-business">To 业务：{{ businessPerson }}</span>
            </div>
          </section>

          <!-- 机箱规格：形态、盘位、背板、电源、总价（型号已在标题块，不重复） -->
          <section class="ss-section">
            <div class="ss-section-title">{{ labels.chassis_title }}</div>
            <div class="ss-spec-grid">
              <div class="spec-item"><span class="spec-key">{{ labels.chassis_form }}</span><span class="spec-val">{{ cfg.chassis_form || '—' }}</span></div>
              <div class="spec-item"><span class="spec-key">{{ labels.chassis_bays }}</span><span class="spec-val">{{ cfg.chassis_bays || '—' }}</span></div>
              <div class="spec-item"><span class="spec-key">{{ labels.chassis_backplane }}</span><span class="spec-val">{{ cfg.backplane_type || 'Pass-Thru' }}</span></div>
              <div class="spec-item"><span class="spec-key">{{ labels.chassis_power }}</span><span class="spec-val">{{ cfg.power_supply || '—' }}</span></div>
              <div v-if="opts.show_chassis_total" class="spec-item spec-total">
                <span class="spec-key">{{ labels.chassis_total }}</span><span class="spec-val">{{ money(cfg.l6_total) }}</span>
              </div>
            </div>
          </section>

          <!-- KP 配件 -->
          <section v-if="cfg.kp_details?.length" class="ss-section">
            <div class="ss-section-title">{{ labels.kp_title }}</div>
            <table class="ss-table">
              <thead>
                <tr>
                  <th class="col-cat">{{ labels.kp_catalogue }}</th><th class="col-desc">{{ labels.kp_description }}</th>
                  <th class="col-qty">{{ labels.kp_qty }}</th><th v-if="opts.show_price_column" class="col-cost">{{ labels.kp_cost }}</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="g in groupByCategory(cfg.kp_details)" :key="g.category">
                  <tr v-for="(item, i) in g.items" :key="i" :class="{ 'group-first': i === 0 }">
                    <td class="cell-cat">{{ g.category }}</td>
                    <td class="cell-desc">{{ getKpDesc(item) }}</td>
                    <td class="cell-qty">{{ item.qty }}</td>
                    <td v-if="opts.show_price_column" class="cell-cost">
                      {{ money((item.final_price || 0) * (item.qty || 0)) }}
                    </td>
                  </tr>
                </template>
                <tr v-if="opts.show_kp_subtotal" class="ss-subtotal">
                  <td colspan="3">{{ labels.kp_subtotal }}</td>
                  <td v-if="opts.show_price_column" class="ss-subtotal-price">{{ money(cfg.kp_total) }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <!-- Warranty 维保 -->
          <section v-if="cfg.warranty_details?.length" class="ss-section">
            <div class="ss-section-title">Warranty</div>
            <table class="ss-table">
              <thead>
                <tr>
                  <th class="col-cat">类别</th><th class="col-desc">描述</th>
                  <th class="col-qty">数量</th><th v-if="opts.show_price_column" class="col-cost">单价</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="g in groupByCategory(cfg.warranty_details)" :key="g.category">
                  <tr v-for="(item, i) in g.items" :key="i" :class="{ 'group-first': i === 0 }">
                    <td class="cell-cat">{{ g.category }}</td>
                    <td class="cell-desc">{{ item.catalogue }}</td>
                    <td class="cell-qty">{{ item.qty }}</td>
                    <td v-if="opts.show_price_column" class="cell-cost">
                      {{ money(item.final_price) }}
                    </td>
                  </tr>
                </template>
                <tr v-if="opts.show_kp_subtotal && cfg.warranty_total" class="ss-subtotal">
                  <td colspan="3">Warranty 合计</td>
                  <td v-if="opts.show_price_column" class="ss-subtotal-price">{{ money(cfg.warranty_total) }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <!-- 维保条款描述 -->
          <section v-if="cfg.warranty_desc_l6 || cfg.warranty_desc_kp" class="ss-section">
            <div class="ss-section-title">Warranty Terms</div>
            <div v-if="cfg.warranty_desc_l6" class="ss-warranty-item">
              <strong>L6维保：</strong>{{ cfg.warranty_desc_l6 }}
            </div>
            <div v-if="cfg.warranty_desc_kp" class="ss-warranty-item">
              <strong>KP维保：</strong>{{ cfg.warranty_desc_kp }}
            </div>
          </section>

          <!-- 配置小计：含税单价 -->
          <section v-if="opts.show_config_subtotal" class="ss-config-subtotal">
            <span>{{ cfg.config_name }} {{ labels.config_subtotal }}</span>
            <span>{{ money(cfg.unit_price) }}</span>
          </section>

          <!-- 含税总价（本配置：含税单价 × 数量） -->
          <section v-if="opts.show_grand_total" class="ss-grand">
            <span class="ss-grand-label">{{ labels.grand_total }}</span>
            <span class="ss-grand-val">{{ money(cfg.total_price) }}</span>
            <span class="ss-grand-qty">（{{ cfg.quantity }}台）</span>
          </section>

          <!-- 报价条款 -->
          <section v-if="opts.show_commercial_terms && terms.length" class="ss-terms">
            <div class="ss-terms-title">报价条款 / Terms</div>
            <div class="ss-terms-grid">
              <div v-for="[label, text] in terms" :key="label" class="ss-terms-item">
                <span class="ss-terms-label">{{ label }}</span>
                <span class="ss-terms-text">{{ text }}</span>
              </div>
            </div>
          </section>

          <!-- 页脚（每页，钉底） -->
          <footer class="ss-footer">
            <div v-if="opts.show_footer_check" class="ss-check">✓ 已通过机型兼容校验</div>
            <div class="ss-contact">
              <span v-if="branding.contact_phone">TEL {{ branding.contact_phone }}</span>
              <span v-if="branding.contact_email">EMAIL {{ branding.contact_email }}</span>
              <span v-if="branding.address">{{ branding.address }}</span>
            </div>
            <div v-if="branding.footer_note" class="ss-footnote">{{ branding.footer_note }}</div>
          </footer>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
/* 文档调色板：固定白底深字，不跟随 app 主题，浅/深色与打印一致 */
.spec-sheet {
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  padding: 20mm 15mm;
  display: flex;
  flex-direction: column;
  gap: 20px;
  background: #ffffff;
  border: 1px solid #E5E7EB;
  box-shadow: 0 10px 40px rgba(15, 23, 42, .12);
  color: #1F2329;
  box-sizing: border-box;
}

/* 多配置模式：外层退化为透明堆叠容器，每配置独占一张 A4 页 */
.spec-sheet--multi {
  width: auto;
  min-height: auto;
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
  align-items: center;
  gap: 24px;
}
.ss-page {
  width: 210mm;
  min-height: 297mm;
  padding: 14mm 15mm;
  background: #ffffff;
  border: 1px solid #E5E7EB;
  box-shadow: 0 10px 40px rgba(15, 23, 42, .12);
  color: #1F2329;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  page-break-after: always;
}
.ss-page:last-child { page-break-after: auto; }

/* 抬头 */
.ss-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  padding-bottom: 16px; border-bottom: 1px solid #1668C0; }
.ss-brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.ss-logo { width: 48px; height: 48px; object-fit: contain; border-radius: 6px; background: #fff; }
.ss-company { font-size: 16px; font-weight: 700; color: #1F2329; }
.ss-tagline { font-size: 11px; color: #6B7280; margin-top: 2px; }
.ss-doc { text-align: right; }
.ss-doc-title { font-size: 14px; font-weight: 700; color: #1668C0; }
.ss-doc-meta { font-size: 11px; color: #6B7280; margin-top: 4px; }

/* 标题块 */
.ss-title-block { position: relative; padding: 4px 0 4px 14px; border-left: 4px solid #1668C0; }
.ss-title-block--inline { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.ss-title-block--inline .ss-title-left { display: flex; align-items: center; gap: 10px; }
.ss-title-block--inline .ss-title-right { margin-top: 0; }
.ss-title-name { font-size: 24px; font-weight: 700; color: #111418; line-height: 1.2; }
.ss-title-sub { font-size: 12px; color: #6B7280; margin-top: 6px; }
.ss-title-right { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.ss-chip { display: inline-block; padding: 2px 10px; font-size: 11px; font-weight: 600;
  color: #1668C0; background: #EAF2FB; border: 1px solid #BCD6F5; border-radius: 999px; }
.ss-to-business { font-size: 12px; color: #64748b; margin-left: 8px; }
.ss-qty-badge { font-size: 12px; color: #64748b; }

/* 配置块标题 - 简约卡片风格 */
.ss-config-block { margin-bottom: 20px; }
.ss-config-title {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 8px;
  margin-bottom: 16px;
  border: 1px solid #e2e8f0;
}
.ss-config-index {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; background: #3b82f6; color: #fff;
  border-radius: 6px; font-size: 12px; font-weight: 600;
}
.ss-config-name { font-size: 15px; font-weight: 600; color: #1e293b; }
.ss-config-qty { font-size: 13px; color: #64748b; margin-left: auto; }

/* 配置小计 */
.ss-config-subtotal { display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-top: 1px solid #E5E7EB; margin-top: 12px;
  font-weight: 600; color: #111418; }
.ss-config-subtotal span:last-child { font-size: 16px; color: #1668C0; font-weight: 700; }

/* 段落标题 */
.ss-section { display: flex; flex-direction: column; gap: 8px; }
.ss-section-title { font-size: 12px; font-weight: 700; letter-spacing: .6px; text-transform: uppercase;
  color: #1668C0; border-bottom: 1px solid #E5E7EB; padding-bottom: 6px; }

/* 机箱摘要：2 列 key:value 网格（避免短值右侧大片留白） */
.ss-spec-grid { display: grid; grid-template-columns: 1fr 1fr; width: 100%; font-size: 13px; }
.ss-spec-grid .spec-item { display: flex; gap: 10px; padding: 9px 10px; border-bottom: 1px solid #EEF0F3; }
.ss-spec-grid .spec-key { color: #6B7280; font-weight: 500; white-space: nowrap; }
.ss-spec-grid .spec-val { color: #1F2329; font-weight: 500; word-break: break-word; }
.ss-spec-grid .spec-total { grid-column: span 2; border-bottom: none; border-top: 1px solid #E5E7EB; font-variant-numeric: tabular-nums; }
.ss-spec-grid .spec-total .spec-key { color: #111418; font-weight: 700; }
.ss-spec-grid .spec-total .spec-val { color: #1668C0; font-weight: 700; font-size: 15px; }

/* KP BOM 表 */
.ss-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ss-table thead th { padding: 8px 10px; text-align: left; font-weight: 700; font-size: 11px;
  text-transform: uppercase; letter-spacing: .4px; color: #6B7280;
  background: #F7F8FA; border-bottom: 1px solid #E5E7EB; }
.ss-table tbody td { padding: 6px 10px; border-bottom: 1px solid #EEF0F3; color: #1F2329; line-height: 1.38; }
.col-cat { width: 16%; }
.col-desc { width: 52%; }
.ss-table .col-qty { width: 10%; text-align: center; }
.ss-table .col-cost { width: 22%; text-align: right; }
.cell-cat { color: #6B7280; font-weight: 500; white-space: nowrap; }
.cell-desc { color: #1F2329; font-weight: 500; word-break: break-word; }
.cell-qty { text-align: center; color: #6B7280; }
.cell-cost { text-align: right; color: #1668C0; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
/* 组分隔：每个分类首行顶部加细线（第一组除外） */
.ss-table tbody tr.group-first td { border-top: 2px solid #E5E7EB; }
.ss-table tbody tr.group-first:first-child td { border-top: none; }
.ss-subtotal td { padding: 11px 10px; font-weight: 700; color: #111418;
  border-bottom: none; border-top: 1px solid #E5E7EB; font-variant-numeric: tabular-nums; }
.ss-subtotal td.ss-subtotal-price { color: #1668C0; text-align: right; font-size: 15px; }
.ss-empty { padding: 18px; text-align: center; font-size: 12px; color: #9CA3AF;
  background: #F7F8FA; border: 1px dashed #D1D5DB; border-radius: 8px; }

/* 维保条款：小字紧凑 */
.ss-warranty-item { font-size: 12px; color: #4B5563; line-height: 1.5; }
.ss-warranty-item strong { color: #1F2329; font-weight: 600; }

/* 报价条款：紧凑 2 列，给整页留出空间 */
.ss-terms { padding: 9px 12px; background: #F7F8FA; border: 1px solid #E5E7EB; border-radius: 6px; }
.ss-terms-title { font-size: 11px; font-weight: 700; letter-spacing: .5px; color: #1668C0;
  text-transform: uppercase; margin-bottom: 6px; }
.ss-terms-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; }
.ss-terms-item { font-size: 11px; line-height: 1.5; color: #4B5563; display: flex; gap: 6px; align-items: baseline; }
.ss-terms-label { color: #1F2329; font-weight: 600; white-space: nowrap; flex: 0 0 5em; }
.ss-terms-text { word-break: break-word; }

/* 合计：柔和边框 */
.ss-grand { display: flex; justify-content: flex-end; align-items: baseline; gap: 14px;
  padding: 13px 16px; border-top: 1px solid #E5E7EB; }
.ss-grand-label { font-size: 13px; font-weight: 600; color: #1F2329; }
.ss-grand-val { font-size: 22px; font-weight: 700; color: #1668C0; font-variant-numeric: tabular-nums; }
.ss-grand-qty { font-size: 14px; font-weight: 600; color: #6B7280; }

/* 页脚 */
.ss-footer { display: flex; flex-direction: column; gap: 6px; padding-top: 14px; border-top: 1px solid #E5E7EB; }
.ss-check { font-size: 12px; font-weight: 600; color: #1668C0; }
.ss-contact { display: flex; flex-wrap: wrap; gap: 14px; font-size: 11px; color: #6B7280; }
.ss-footnote { font-size: 11px; color: #9CA3AF; }
</style>

<!-- 非 scoped：打印规则需跳出 scoped 边界，锚点 .spec-sheet-root 由父级加在组件根上。
     屏内已是白底深字文档配色，打印只需去阴影/边框、撑满页面、分页避让。 -->
<style>
@media print {
  /* 隐藏 body 下所有非规格书元素 */
  body > *:not(.spec-sheet-overlay) {
    display: none !important;
  }

  /* 规格书 overlay：移除 fixed 定位、backdrop-filter、inset */
  .spec-sheet-overlay {
    position: static !important;
    inset: auto !important;
    z-index: auto !important;
    background: #fff !important;
    backdrop-filter: none !important;
    padding: 0 !important;
    overflow: visible !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
  }

  /* 滚动容器 */
  .spec-sheet-scroll {
    display: flex !important;
    max-width: none !important;
    max-height: none !important;
    overflow: visible !important;
    gap: 0 !important;
    align-items: center !important;
    padding: 0 !important;
    width: 100% !important;
  }

  /* 规格书根元素 */
  .spec-sheet-root {
    position: static !important;
    margin: 0 auto !important;
    padding: 0 !important;
    background: #fff !important;
    box-shadow: none !important;
    border: none !important;
    border-radius: 0 !important;
  }

  /* 规格书内容 */
  .spec-sheet-root .spec-sheet {
    box-shadow: none !important;
    border: none !important;
    border-radius: 0 !important;
    max-width: none !important;
    padding: 0 !important;
  }

  /* 多配置模式：容器改 block 以保证分页可靠，每页去装饰靠 @page margin 留白 */
  .spec-sheet-root.spec-sheet--multi {
    display: block !important;
  }
  .spec-sheet-root .ss-page {
    box-shadow: none !important;
    border: none !important;
    padding: 0 !important;
    min-height: auto !important;
    width: 100% !important;
    overflow: hidden !important;
    /* 按配置页自然高度等比缩放到一页：--print-scale/--print-h 由打印前 JS 写入 */
    transform: scale(var(--print-scale, 1));
    transform-origin: top center;
    height: var(--print-h, auto);
  }

  /* 隐藏工具栏 */
  .spec-sheet-toolbar,
  .ss-no-print {
    display: none !important;
  }

  @page {
    size: A4;
    margin: 14mm;
  }

  .spec-sheet-root .ss-section,
  .spec-sheet-root table {
    page-break-inside: avoid;
  }

  .spec-sheet-root tr {
    page-break-inside: avoid;
  }
}
</style>
