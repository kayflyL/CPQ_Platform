import { ref, computed, type ComputedRef } from 'vue'
import { kpPartsApi, type KpPart } from '@/api/serverConfig'
import { fromKpPart } from '@/composables/usePartAdapter'
import type { PickerItem } from '@/types/picker'
import { useQuoteStore, type ConfigData, type Item } from '@/store/quote'

type QuoteStore = ReturnType<typeof useQuoteStore>

export const CORE_KP_CATS = ['CPU', 'Memory', 'HDD/SSD', 'GPU', 'NIC']

export function useQuoteKpCatalog(store: QuoteStore, activeConfig: ComputedRef<ConfigData | undefined>) {
  const kpCategories = ref<{ id: number; name: string }[]>([])
  const kpCatalog = ref<Record<string, KpPart[]>>({})
  let loaded = false

  async function loadKpCatalog() {
    if (loaded) return
    try {
      kpCategories.value = await kpPartsApi.categories()
      const results = await Promise.all(kpCategories.value.map((c) => kpPartsApi.listByCategory(c.id)))
      kpCategories.value.forEach((c, i) => {
        kpCatalog.value[c.name] = results[i]
      })
      loaded = true
    } catch (e) {
      console.warn('加载 KP 料号目录失败', e)
    }
  }

  const pickerCatalog = computed<Record<string, PickerItem[]>>(() => {
    const out: Record<string, PickerItem[]> = {}
    for (const [cat, list] of Object.entries(kpCatalog.value)) {
      out[cat] = (list || []).map(fromKpPart)
    }
    return out
  })

  function kpPartByPn(pn: string): KpPart | undefined {
    for (const c of kpCategories.value) {
      const found = (kpCatalog.value[c.name] || []).find((p) => p.pn === pn)
      if (found) return found
    }
    return undefined
  }

  function priceOf(pn: string): number {
    return kpPartByPn(pn)?.unit_price || 0
  }

  function kpCardCatsFor(cfg: ConfigData): string[] {
    const seen = new Set<string>()
    const out: string[] = []
    const itemsCats = (cfg.items || [])
      .filter((i: any) => i.category === 'Key Parts')
      .map((i: any) => i.part_category)
    for (const c of [...CORE_KP_CATS, ...itemsCats]) {
      if (c && !seen.has(c)) {
        seen.add(c)
        out.push(c)
      }
    }
    return out
  }

  function kpLinesForCat(cfg: ConfigData, cat: string): Item[] {
    return (cfg.items || []).filter((i: any) => i.category === 'Key Parts' && i.part_category === cat)
  }

  function kpGlobalIndex(cfg: ConfigData, cat: string, localIdx: number): number {
    let seen = 0
    for (let gi = 0; gi < cfg.items.length; gi++) {
      const it = cfg.items[gi]
      if (it.category !== 'Key Parts' || it.part_category !== cat) continue
      if (seen === localIdx) return gi
      seen++
    }
    return -1
  }

  function newKpItem(cat: string): Item {
    const part = (kpCatalog.value[cat] || [])[0]
    return {
      category: 'Key Parts',
      part_category: cat,
      pn: part?.pn || '',
      catalogue: part?.name || '',
      description: '',
      qty: 1,
      base_price: part?.unit_price || 0,
      profit_margin: 10,
      final_price: 0,
      currency: 'RMB',
    }
  }

  function onKpSetLine(cfg: ConfigData, cat: string, localIdx: number, patch: Partial<Item>) {
    const gi = kpGlobalIndex(cfg, cat, localIdx)
    if (gi < 0) return
    Object.assign(cfg.items[gi], patch)
    if (patch.pn) {
      const part = kpPartByPn(patch.pn)
      if (part) cfg.items[gi].catalogue = part.name
    }
    store.recalculateAll()
  }

  function onKpDelLine(cfg: ConfigData, cat: string, localIdx: number) {
    const gi = kpGlobalIndex(cfg, cat, localIdx)
    if (gi >= 0) cfg.items.splice(gi, 1)
    store.recalculateAll()
  }

  function onKpAddLine(cfg: ConfigData, cat: string) {
    cfg.items.push(newKpItem(cat))
    store.recalculateAll()
  }

  function onKpRemoveCard(cfg: ConfigData, cat: string) {
    cfg.items = cfg.items.filter((i: any) => !(i.category === 'Key Parts' && i.part_category === cat))
    store.recalculateAll()
  }

  const availableKpCats = computed(() => {
    const cfg = activeConfig.value
    if (!cfg) return []
    const shown = new Set(kpCardCatsFor(cfg))
    return kpCategories.value.filter((c) => !shown.has(c.name))
  })

  const pendingNewKpCat = ref('')
  function onAddKpCard() {
    const cfg = activeConfig.value
    const cat = pendingNewKpCat.value
    pendingNewKpCat.value = ''
    if (!cfg || !cat) return
    cfg.items.push(newKpItem(cat))
    store.recalculateAll()
  }

  return {
    kpCategories,
    kpCatalog,
    pickerCatalog,
    kpPartByPn,
    priceOf,
    kpCardCatsFor,
    kpLinesForCat,
    kpGlobalIndex,
    newKpItem,
    onKpSetLine,
    onKpDelLine,
    onKpAddLine,
    onKpRemoveCard,
    availableKpCats,
    pendingNewKpCat,
    onAddKpCard,
    loadKpCatalog,
  }
}
