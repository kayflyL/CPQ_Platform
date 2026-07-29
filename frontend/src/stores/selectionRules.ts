/**
 * 选型规则引擎 Pinia Store。
 *
 * 兼容性规则引擎（WHEN→THEN）：读 /api/compatibility-rules，对配置 context 跑声明式规则，
 * 返回动作清单（require/exclude/derive/filter/recommend）。纯求值逻辑在 selectionEngine.ts（可独立单测）。
 *
 * body schema（见 backend compatibility_rule_repo.DEFAULT_RULES）：
 *   when: { all?:[cond], any?:[cond] } | cond   cond = { field, op, value }
 *   then: { action, ... }   action ∈ require/exclude/derive/filter/recommend
 *   字段寻址：kp.<category>.qty / kp.<category>.spec.<key> / config.series / config.sata_qty / opportunity.platform_type
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { compatibilityRulesApi, type CompatibilityRule } from '@/api/compatibilityRules'
import { evaluateRules as _evaluateRules, type RuleAction, type RuleContext } from './selectionEngine'

// 纯求值逻辑与类型统一由 selectionEngine 提供；re-export 供消费端从 store 统一 import
export type { RuleAction, RuleActionKind, RuleSeverity, RuleContext } from './selectionEngine'

export const useSelectionRulesStore = defineStore('selectionRules', () => {
  const _creRules = ref<CompatibilityRule[]>([])
  const _creLoaded = ref(false)
  let _crePromise: Promise<void> | null = null

  /** 加载兼容性规则（幂等）。编辑器改完后调 invalidateRules 让消费端重读。 */
  async function ensureRules(): Promise<void> {
    if (_creLoaded.value) return
    if (!_crePromise) {
      _crePromise = compatibilityRulesApi.list({ status: 'active' })
        .then(r => { _creRules.value = r.rules || [] })
        .catch(() => { _creRules.value = [] })
        .finally(() => { _creLoaded.value = true })
    }
    return _crePromise
  }

  /** 编辑器改完规则后调用：清缓存并立即重拉，消费端的 selectionActions computed 自动刷新。 */
  async function invalidateRules(): Promise<void> {
    _creLoaded.value = false
    _creRules.value = []
    _crePromise = null
    return ensureRules()
  }

  /** 对一组配置 context 跑全部 active 兼容性规则，返回命中动作清单。 */
  function evaluateRules(ctx: RuleContext): RuleAction[] {
    return _evaluateRules(_creRules.value, ctx)
  }

  const creRules = computed(() => _creRules.value)

  return {
    creRules,
    ensureRules,
    invalidateRules,
    evaluateRules,
  }
})
