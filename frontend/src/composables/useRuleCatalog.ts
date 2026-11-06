import { ref, computed, onMounted } from 'vue'
import { compatibilityRulesApi, type CompatibilityRule } from '@/api/compatibilityRules'
import { RULE_CATEGORY_SEED, RULE_OP_MAP, humanizeFieldPath } from '@/constants/ruleMeta'

export function useRuleCatalog() {
  const rules = ref<CompatibilityRule[]>([])
  const loading = ref(false)
  const searchText = ref('')

  const seedFirstSort = (a: string, b: string) => {
    const sa = RULE_CATEGORY_SEED.indexOf(a), sb = RULE_CATEGORY_SEED.indexOf(b)
    if (sa >= 0 || sb >= 0) { if (sa < 0) return 1; if (sb < 0) return -1; return sa - sb }
    return a.localeCompare(b, 'zh')
  }

  const categoryOpts = computed(() =>
    [...new Set(rules.value.map(r => r.category).filter(Boolean) as string[])]
      .sort(seedFirstSort).map(c => ({ value: c, label: c }))
  )

  function whenSummary(b: any): string {
    const w = b?.when
    if (!w || (!w.all && !w.any && !w.field)) return '始终生效'
    const conds: any[] = w.field ? [w] : (w.all || w.any || [])
    const joiner = Array.isArray(w.any) ? ' 或 ' : ' 且 '
    const parts = conds.map((c: any) => {
      const field = humanizeFieldPath(c.field)
      const op = RULE_OP_MAP[c.op] || c.op
      let val: any = c.value
      if (typeof val === 'string' && /^(kp|config|opportunity)\./.test(val)) val = humanizeFieldPath(val)
      return `${field} ${op} ${val}`
    })
    return parts.join(joiner) + ' 时'
  }

  const searched = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return rules.value
    return rules.value.filter(r =>
      r.name.toLowerCase().includes(q) ||
      (whenSummary(r.body) || '').toLowerCase().includes(q)
    )
  })

  function groupRules(list: CompatibilityRule[]) {
    const map = new Map<string, CompatibilityRule[]>()
    for (const r of list) {
      const key = r.category || '__none__'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return [...map.entries()]
      .map(([key, rs]) => ({ key, category: key === '__none__' ? '' : key, rules: rs }))
      .sort((a, b) => {
        if (a.key === '__none__') return 1
        if (b.key === '__none__') return -1
        return seedFirstSort(a.category, b.category)
      })
  }

  async function load() {
    loading.value = true
    try {
      const r = await compatibilityRulesApi.list()
      rules.value = r.rules || []
    } catch {
      rules.value = []
    } finally {
      loading.value = false
    }
  }
  onMounted(load)

  return {
    rules, loading, load,
    searchText, categoryOpts, whenSummary,
    searched, groupRules,
  }
}
