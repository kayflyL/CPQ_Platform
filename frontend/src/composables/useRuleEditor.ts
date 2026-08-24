import { ref, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { compatibilityRulesApi, type CompatibilityRule } from '@/api/compatibilityRules'
import { kpPartsApi } from '@/api/serverConfig'

export interface RuleEditorOptions {
  rules: () => CompatibilityRule[]
  afterChange: () => Promise<void>
}

export function useRuleEditor(opts: RuleEditorOptions) {
  const kpCats = ref<string[]>([])
  const kpSpecKeys = ref<Record<string, string[]>>({})

  async function loadKpMeta() {
    try {
      const [cats, sk] = await Promise.all([kpPartsApi.categories(), kpPartsApi.specKeys()])
      kpCats.value = (cats || []).map(c => c.name).filter(Boolean)
      kpSpecKeys.value = sk || {}
    } catch {
      kpCats.value = []
      kpSpecKeys.value = {}
    }
  }

  const fieldOpts = computed(() => {
    const kp: { value: string; label: string }[] = []
    for (const c of kpCats.value) {
      kp.push({ value: `kp.${c}.qty`, label: `kp.${c}.qty` })
      for (const k of (kpSpecKeys.value[c] || [])) {
        kp.push({ value: `kp.${c}.spec.${k}`, label: `kp.${c}.spec.${k}` })
      }
    }
    for (const f of ['config.series', 'config.model', 'config.form', 'config.sata_qty', 'config.sas_qty', 'config.nvme_qty', 'config.drive_kinds', 'config.bp_type']) {
      kp.push({ value: f, label: f })
    }
    return kp
  })

  const filterFn = (input: string, option: any) => {
    const opt = typeof option === 'string' ? option : String(option?.value ?? option?.label ?? '')
    return opt.toLowerCase().includes((input || '').toLowerCase())
  }

  const editing = ref<CompatibilityRule | null>(null)
  const isNew = ref(false)
  const saving = ref(false)
  const form = ref<any>({})
  const editModalVisible = ref(false)

  function blankForm(): any {
    return {
      name: '', type: 'derive', status: 'active', category: '', regions: [],
      whenAll: [{ field: '', op: '>=', value: '' }],
      target: '', min_qty: '', unique_field: 'pn', specKey: '', specVal: '',
      basis: '', per: 1, round: 'ceil', deriveMode: 'calc', assignField: 'config.bp_type', assignValue: '',
      fScope: 'server_model', fField: 'series', fOp: '==', fValue: 'opportunity.platform_type',
      desc: '',
    }
  }

  function openNew(category?: string) {
    isNew.value = true
    editing.value = { id: 0, domain: 'selection', type: 'derive', name: '', scope: null, body: {}, status: 'active', version: 1, hit_count: 0, last_hit_at: null }
    form.value = blankForm()
    if (category) form.value.category = category
    editModalVisible.value = true
  }

  function openEdit(r: CompatibilityRule) {
    isNew.value = false
    editing.value = r
    const b = r.body || {}
    const w = b.when || {}
    const whenAll = Array.isArray(w.all) ? w.all.map((c: any) => ({ field: c.field || '', op: c.op || '>=', value: c.value ?? '' }))
      : (w.field ? [{ field: w.field, op: w.op || '>=', value: w.value ?? '' }] : [{ field: '', op: '>=', value: '' }])
    const t = b.then || {}
    form.value = {
      name: r.name, type: r.type, status: r.status, category: r.category || '', regions: r.regions || [], whenAll,
      target: t.target || '', min_qty: t.min_qty || '', unique_field: t.unique_field || 'pn',
      specKey: t.spec_constraint ? Object.keys(t.spec_constraint)[0] || '' : '',
      specVal: t.spec_constraint ? String(Object.values(t.spec_constraint)[0] ?? '') : '',
      basis: t.basis || '', per: t.per || 1, round: t.round || 'ceil',
      deriveMode: (t.field && 'value' in t) ? 'assign' : 'calc', assignField: t.field || 'config.bp_type', assignValue: t.value ?? '',
      fScope: t.scope || 'server_model', fField: t.field || 'series', fOp: t.op || '==', fValue: t.value || 'opportunity.platform_type',
      desc: b.desc || r.description || '',
    }
    editModalVisible.value = true
  }

  function closeEdit() {
    editModalVisible.value = false
    editing.value = null
    isNew.value = false
    form.value = blankForm()
  }

  function buildBody(): any {
    const f = form.value
    const whenAll = (f.whenAll || []).filter((c: any) => c.field).map((c: any) => ({ field: c.field, op: c.op, value: c.value }))
    const when = whenAll.length === 0 ? {} : (whenAll.length === 1 ? whenAll[0] : { all: whenAll })
    let then: any
    switch (f.type) {
      case 'require':
        then = { action: 'require', target: f.target }
        if (f.min_qty) then.min_qty = f.min_qty
        if (f.specKey && f.specVal) then.spec_constraint = { [f.specKey]: f.specVal }
        break
      case 'exclude': then = { action: 'exclude', target: f.target, unique_field: f.unique_field || 'pn' }; break
      case 'derive':
        then = f.deriveMode === 'assign'
          ? { action: 'derive', field: f.assignField, value: f.assignValue }
          : { action: 'derive', target: f.target, basis: f.basis, per: Number(f.per) || 1, round: f.round }
        break
      case 'filter': then = { action: 'filter', scope: f.fScope, field: f.fField, op: f.fOp, value: f.fValue }; break
      case 'recommend': then = { action: 'recommend', target: f.target }; break
    }
    return { when, then, desc: f.desc || form.value.name }
  }

  async function save() {
    const f = form.value
    if (!f.name?.trim()) { message.warning('请填规则名称'); return }
    const needTarget = f.type === 'require' || f.type === 'exclude' || f.type === 'recommend' || (f.type === 'derive' && f.deriveMode !== 'assign')
    if (needTarget && !f.target?.trim()) {
      message.warning('请填目标（如 kp.GPU）'); return
    }
    if (f.type === 'derive' && f.deriveMode === 'assign' && !String(f.assignValue ?? '').trim()) {
      message.warning('请填赋值的值（如 tri）'); return
    }
    const body = buildBody()
    const category = f.category?.trim() || null
    saving.value = true
    try {
      if (!isNew.value && editing.value?.id) {
        await compatibilityRulesApi.update(editing.value.id, { name: f.name, body, status: f.status, category, regions: f.regions || [] })
      } else {
        await compatibilityRulesApi.create({ type: f.type, name: f.name, body, status: f.status, category, regions: f.regions || [] })
      }
      message.success('已保存，已即时生效')
      closeEdit()
      await opts.afterChange()
    } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
    finally { saving.value = false }
  }

  function remove(r: CompatibilityRule) {
    Modal.confirm({
      title: '删除规则？', content: r.name, okText: '删除', okType: 'danger', cancelText: '取消',
      onOk: async () => { try { await compatibilityRulesApi.remove(r.id); message.success('已删除'); await opts.afterChange() } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') } },
    })
  }

  async function toggleStatus(r: CompatibilityRule) {
    const next = r.status === 'active' ? 'archived' : 'active'
    if (r.status === 'active') {
      const ok = await new Promise<boolean>(resolve => {
        Modal.confirm({
          title: '停用规则？',
          content: '停用后该规则会立即退出报价 / 配置校验，确认停用？',
          okText: '停用', okType: 'danger', cancelText: '取消',
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
      if (!ok) return
    }
    try { await compatibilityRulesApi.setStatus(r.id, next as any); await opts.afterChange() } catch (e: any) { message.error('操作失败') }
  }

  function downloadCurrentRules() {
    const blob = new Blob([JSON.stringify(opts.rules(), null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `compatibility-rules-backup-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function resetDefaults() {
    Modal.confirm({
      title: '重置为默认规则？',
      content: '将先下载当前规则备份，再清空全部兼容性规则并恢复系统 seed。此操作不可撤销。',
      okText: '重置', okType: 'danger', cancelText: '取消',
      onOk: async () => {
        downloadCurrentRules()
        try { await compatibilityRulesApi.reset(); message.success('已重置'); await opts.afterChange() } catch (e: any) { message.error(e.response?.data?.detail || '重置失败') }
      },
    })
  }

  function addCond() { form.value.whenAll.push({ field: '', op: '>=', value: '' }) }
  function delCond(i: number | string) { form.value.whenAll.splice(Number(i), 1) }

  onMounted(loadKpMeta)

  return {
    fieldOpts, filterFn,
    editing, isNew, saving, form, editModalVisible,
    openNew, openEdit, closeEdit, save, remove, toggleStatus, resetDefaults, addCond, delCond,
  }
}
