/**
 * useSelectionGate — 报价工作台消费选型配置引擎(单一判定出口)。
 *
 * 已选 KP 行/机型变化 → 防抖调 /api/selection-gate/resolve(唯一判定出口,前端不本地求值)。
 * 暴露:violations/recommends/derived/budget、各类目「合规候选名集合」(配置面只显合规件,
 * 只留过滤统计)、gateDegraded(引擎不可达=fail-open 降级但白盒可见)。
 */
import { ref, watch, onUnmounted, type Ref } from 'vue'
import { selectionGateApi, type ResolveResult, type GatePartInput, type GateAction, type GateViolation } from '@/api/selectionGate'
import { useDebounceFn } from '@vueuse/core'

export interface GateAlertView {
  ruleId: number | null
  ruleName: string
  action: string
  severity: string
  desc: string
  offenders?: string[]
}

const ALERT_SEVERITY_ORDER: Record<string, number> = { conflict: 0, require: 1, warning: 2, info: 3 }

/** 门禁输出 → 选型建议列表(硬违规在前)。 */
export function gateAlertsOf(
  violations: Ref<GateViolation[]>,
  recommends: Ref<GateAction[]>,
): GateAlertView[] {
  const hard = (violations.value || []).map(v => ({
    ruleId: v.ruleId,
    ruleName: v.ruleName,
    action: v.action,
    severity: v.severity === 'require' ? 'require' : 'conflict',
    desc: v.desc,
    offenders: v.offenders,
  }))
  const soft = (recommends.value || []).map(r => ({
    ruleId: r.ruleId,
    ruleName: r.ruleName,
    action: 'recommend',
    severity: (r.severity as string) || 'info',
    desc: r.desc,
    offenders: r.offenders,
  }))
  return [...hard, ...soft].sort(
    (a, b) => (ALERT_SEVERITY_ORDER[a.severity] ?? 9) - (ALERT_SEVERITY_ORDER[b.severity] ?? 9),
  )
}

export interface UseSelectionGateOptions {
  /** 当前配置解析到的 base_config id(未关联机型 = null → 引擎不判平台,只跑规则) */
  baseConfigId: () => number | null | undefined
  /** 机型系列(平台判定主键之一) */
  series: () => string
  /** 机型名(机型级 compat 判定用) */
  serverModel: () => string
  /** 已选 KP 行(含 specs,供功耗/盘协议判定;未关联机型的类目也传) */
  kpRows: () => GatePartInput[]
}

export function useSelectionGate(opts: UseSelectionGateOptions) {
  const violations = ref<GateViolation[]>([])
  const recommends = ref<GateAction[]>([])
  const derived = ref<GateAction[]>([])
  const budget = ref<ResolveResult['budget'] | null>(null)
  /** 类目 → 合规候选名集合(引擎不可达/该类目无数据时为空 = 不过滤) */
  const allowedNames = ref<Record<string, Set<string>>>({})
  /** 类目 → 被过滤件数(下拉顶部过滤统计小字) */
  const filteredCount = ref<Record<string, number>>({})
  const gateDegraded = ref(false)
  const gateRunning = ref(false)
  let seq = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  async function run() {
    const mySeq = ++seq
    const bcId = opts.baseConfigId() ?? null
    gateRunning.value = true
    try {
      const r = await selectionGateApi.resolve({
        base_config_id: bcId,
        parts: opts.kpRows() || [],
        options: true,
      })
      if (mySeq !== seq) return
      violations.value = r.violations || []
      recommends.value = r.recommends || []
      derived.value = r.derived || []
      budget.value = r.budget || null
      const names: Record<string, Set<string>> = {}
      const counts: Record<string, number> = {}
      for (const [cat, o] of Object.entries(r.options || {})) {
        names[cat] = new Set((o.allowed || []).map(a => a.model))
        counts[cat] = (o.blocked || []).length
      }
      allowedNames.value = names
      filteredCount.value = counts
      gateDegraded.value = false
    } catch {
      if (mySeq !== seq) return
      // 降级纪律:引擎不可达 = 放行(不过滤不拦),白盒可见
      violations.value = []
      recommends.value = []
      derived.value = []
      budget.value = null
      allowedNames.value = {}
      filteredCount.value = {}
      gateDegraded.value = true
    } finally {
      if (mySeq === seq) gateRunning.value = false
    }
  }

  const refresh = useDebounceFn(run, 500)

  // 监听轻量签名(类目:PN:数量 拼接串),禁用 deep——deep 会把每次构造的 kpRows 数组
  // (含 200+ 件 specs 对象)整棵深遍历并逐属性注册依赖,组件多的页面每次响应式更新都被
  // 重扫一遍,表现为页面卡顿。签名串足以覆盖判定输入的变化。
  watch(
    () => {
      const rows = opts.kpRows() || []
      return [
        opts.baseConfigId() ?? '',
        opts.serverModel() || '',
        opts.series() || '',
        rows.map(r => `${r.category}:${r.pn || r.name || ''}:${r.qty ?? 0}`).join('|'),
      ]
    },
    () => refresh(),
  )

  onUnmounted(() => {
    seq++
    if (timer) clearTimeout(timer)
  })

  return { violations, recommends, derived, budget, allowedNames, filteredCount, gateDegraded, gateRunning, refresh }
}
