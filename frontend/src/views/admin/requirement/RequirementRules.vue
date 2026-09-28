<script setup lang="ts">
defineOptions({ name: 'RequirementRules' })
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import { DeleteOutlined, EditOutlined, PoweroffOutlined } from '@ant-design/icons-vue'
import { compatibilityRulesApi, type CompatibilityRule, type RuleStatus } from '@/api/compatibilityRules'
import { useSeriesStore } from '@/stores/series'

const router = useRouter()
const series = useSeriesStore()
onMounted(() => { series.ensureSeries() })

const rules = ref<CompatibilityRule[]>([])
const loading = ref(false)
const loadError = ref(false)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const r = await compatibilityRulesApi.list({ domain: 'requirement' })
    rules.value = r.rules || []
  } catch {
    loadError.value = true
    message.error('规则加载失败，请重试')
  } finally { loading.value = false }
}
onMounted(load)

// ===== 分桶 + 搜索（名称/信号词/要点/依据）=====
const searchText = ref('')
const platRules = computed(() => rules.value.filter(r => (r.category || '') === '平台归置'))
const sceneRules = computed(() => rules.value.filter(r => (r.category || '') !== '平台归置'))

function hitText(r: CompatibilityRule): string {
  return [r.name, ...signalsOf(r), evidenceOf(r),
    ...itemsOf(r).flatMap(i => [i.category, i.text]), platformOf(r)].join(' ').toLowerCase()
}
const filteredPlat = computed(() => {
  const q = searchText.value.trim().toLowerCase()
  return q ? platRules.value.filter(r => hitText(r).includes(q)) : platRules.value
})
const filteredScene = computed(() => {
  const q = searchText.value.trim().toLowerCase()
  return q ? sceneRules.value.filter(r => hitText(r).includes(q)) : sceneRules.value
})

function countLabel(list: CompatibilityRule[]): string {
  const on = list.filter(r => r.status === 'active').length
  const draft = list.filter(r => r.status === 'draft' || r.status === 'testing').length
  return `${on} 生效${draft ? ` · ${draft} 草稿` : ''}`
}
const platCountLabel = computed(() => countLabel(platRules.value))
const sceneCountLabel = computed(() => countLabel(sceneRules.value))


// ===== 状态展示 =====
const STATUS_META: Record<string, { label: string; cls: string }> = {
  active: { label: '生效中', cls: 'on' },
  draft: { label: '草稿', cls: 'warn' },
  testing: { label: '测试中', cls: 'info' },
  archived: { label: '停用', cls: 'off' },
}
const STATUS_OPTS = [
  { label: '生效中', value: 'active' },
  { label: '草稿', value: 'draft' },
  { label: '测试中', value: 'testing' },
  { label: '停用', value: 'archived' },
]

// ===== 解析（规则 → 表单）=====
function signalsOf(r: CompatibilityRule): string[] {
  const when = r.body?.when || {}
  const list: any[] = (when as any).any || (when as any).all
    || ((when as any).field ? [when] : [])
  return list.filter(c => c && c.op === 'contains').map(c => String(c.value))
}

function platformOf(r: CompatibilityRule): string {
  const then = (r.body?.then || {}) as any
  return String(then.value || '')
}

function itemsOf(r: CompatibilityRule): { category: string; text: string }[] {
  const then = (r.body?.then || {}) as any
  return (then.items || []).map((i: any) => ({ category: String(i.category || ''), text: String(i.text || '') }))
}

function evidenceOf(r: CompatibilityRule): string {
  return String((r.body?.evidence as string) || '')
}

// ===== 表单 =====
const platForm = reactive({
  id: null as number | null,
  name: '',
  status: 'active' as RuleStatus,
  signals: [] as string[],
  platform: '',
  evidence: '',
})
const sceneForm = reactive({
  id: null as number | null,
  name: '',
  status: 'active' as RuleStatus,
  signals: [] as string[],
  items: [] as { category: string; text: string }[],
  evidence: '',
  desc: '',
})
const platOpen = ref(false)
const sceneOpen = ref(false)
const isNew = ref(false)

function openPlat(r?: CompatibilityRule) {
  isNew.value = !r
  platForm.id = r?.id ?? null
  platForm.name = r?.name || ''
  platForm.status = (r?.status || 'active') as RuleStatus
  platForm.signals = signalsOf(r || ({} as CompatibilityRule))
  platForm.platform = platformOf(r || ({} as CompatibilityRule))
  platForm.evidence = evidenceOf(r || ({} as CompatibilityRule))
  platOpen.value = true
}

function openScene(r?: CompatibilityRule) {
  isNew.value = !r
  sceneForm.id = r?.id ?? null
  sceneForm.name = r?.name || ''
  sceneForm.status = (r?.status || 'active') as RuleStatus
  sceneForm.signals = signalsOf(r || ({} as CompatibilityRule))
  sceneForm.items = itemsOf(r || ({} as CompatibilityRule))
  sceneForm.evidence = evidenceOf(r || ({} as CompatibilityRule))
  sceneForm.desc = r?.description || ''
  sceneOpen.value = true
}

function closeAll() {
  platOpen.value = false
  sceneOpen.value = false
}

// ===== 编译保存 =====
function platBody(f: typeof platForm) {
  return {
    when: { any: f.signals.map(w => ({ field: 'kp.CPU.spec.text', op: 'contains', value: w })) },
    then: { action: 'derive', field: 'opportunity.platform_type', value: f.platform },
    desc: '客户点名 CPU 阵营信号 → 平台推导；推导值属推断，须经客户确认',
    evidence: f.evidence.trim(),
  }
}

function sceneBody(f: typeof sceneForm) {
  return {
    when: { any: f.signals.map(w => ({ field: 'config.scenario_blob', op: 'contains', value: w })) },
    then: { action: 'baseline', title: f.name.trim(), items: f.items.filter(i => i.text.trim()) },
    desc: '场景配置基线：AI 推荐配件时照此校准数量与必备件；客户明确给过数量时以客户为准',
    evidence: f.evidence.trim(),
  }
}

async function savePlat() {
  if (!platForm.name.trim() || !platForm.platform || !platForm.signals.length || !platForm.evidence.trim()) {
    message.warning('名称、信号词、推导平台、依据均必填'); return
  }
  const payload: any = {
    type: 'derive', category: '平台归置', name: platForm.name.trim(),
    status: platForm.status, body: platBody(platForm),
  }
  if (platForm.id) await compatibilityRulesApi.update(platForm.id, payload)
  else await compatibilityRulesApi.create({ ...payload, domain: 'requirement' })
  message.success('已保存'); closeAll(); await load()
}

async function saveScene() {
  if (!sceneForm.name.trim() || !sceneForm.signals.length
    || !sceneForm.items.some(i => i.text.trim()) || !sceneForm.evidence.trim()) {
    message.warning('名称、信号词、至少一条要点、依据均必填'); return
  }
  const payload: any = {
    type: 'recommend', category: '场景配置基线', name: sceneForm.name.trim(),
    status: sceneForm.status, body: sceneBody(sceneForm), description: sceneForm.desc || null,
  }
  if (sceneForm.id) await compatibilityRulesApi.update(sceneForm.id, payload)
  else await compatibilityRulesApi.create({ ...payload, domain: 'requirement' })
  message.success('已保存'); closeAll(); await load()
}

async function removeRule(r: CompatibilityRule) {
  Modal.confirm({
    title: `删除规则「${r.name}」？`,
    content: '删除后 AI 注入知识立即少一条依据，不可恢复。',
    okText: '删除', okType: 'danger',
    onOk: async () => { await compatibilityRulesApi.remove(r.id); message.success('已删除'); await load() },
  })
}

async function toggleStatus(r: CompatibilityRule) {
  const next: RuleStatus = r.status === 'active' ? 'archived' : 'active'
  await compatibilityRulesApi.setStatus(r.id, next)
  message.success(next === 'active' ? '已启用' : '已停用')
  await load()
}

// ===== 弹窗标题 =====
const platTitle = computed(() => (platOpen.value && isNew.value ? '新增平台归置' : '编辑平台归置'))
const sceneTitle = computed(() => (sceneOpen.value && isNew.value ? '新增场景基线' : '编辑场景基线'))

function addItem() { sceneForm.items.push({ category: '网卡', text: '' }) }
function delItem(i: number) { sceneForm.items.splice(i, 1) }

const ITEM_CATS = ['网卡', '内存', 'CPU', '系统盘', '电源', 'NVMe 缓存', 'GPU', '硬盘', 'RAID 卡', '网络']
const platformOpts = computed(() => (series.values.length ? series.values : ['Orion', 'Polaris', 'Intel', '工作站'])
  .map(v => ({ label: v, value: v })))
</script>

<template>
  <div class="rrw">
    <div class="rr-bar glass-light">
      <a class="rr-back" @click="router.push('/strategies')">
        <span class="rr-arrow">←</span> 解决方案
      </a>
      <span class="rr-sep">/</span>
      <span class="rr-bar-title">需求分析规则</span>
      <div class="rr-tools">
        <a-input v-model:value="searchText" placeholder="搜索规则名称/信号词/要点" size="small" allow-clear />
      </div>
    </div>

    <div class="rrw-body">
      <div class="rr">
        <div class="rr-head">
          <div>
            <h2 class="rr-title">需求分析规则</h2>
            <p class="rr-sub">服务器配置基线知识：让 AI 出配置时<em>该配什么、配多少</em>有据可依。基线只做推荐依据，<em>客户确认后才落表</em>。</p>
          </div>
        </div>
        <div class="rr-scope">与其它页面的分工：这里管「配得对不对」；选型配置管「配了行不行」（条件硬规则）；BOM 案例库给「成品长什么样」。三者互不重复。</div>
        <div v-if="loadError" class="rr-err">规则加载失败，请检查后端服务后
          <a @click="load">重试</a>
        </div>

    <!-- 大类一：平台归置 -->
    <section class="rr-sec">
      <div class="rr-sec-head">
        <span class="rr-sec-title">平台归置</span>
        <span class="rr-sec-count">{{ platCountLabel }}</span>
        <span class="rr-sec-desc">客户点名 CPU 阵营 → 词典归置平台，AI 按语义就近外推</span>
      </div>
      <a-spin :spinning="loading">
      <div class="rr-grid">
        <div v-for="r in filteredPlat" :key="r.id" class="rr-tile" :class="{ archived: r.status !== 'active' }" @click="openPlat(r)">
          <div class="rr-t-top">
            <span class="rr-dot" :class="STATUS_META[r.status]?.cls" />
            <span class="rr-t-name">{{ r.name }}</span>
            <span v-if="r.status !== 'active'" class="rr-t-state">{{ STATUS_META[r.status]?.label }}</span>
          </div>
          <div class="rr-t-meta">
            <b>平台 {{ platformOf(r) || '？' }}</b> · 信号词 {{ signalsOf(r).length }}
            <template v-if="r.hit_count"> · 命中 {{ r.hit_count }} 次</template>
          </div>
          <div class="rr-t-evi">{{ evidenceOf(r) }}</div>
          <div class="rr-t-foot" @click.stop>
            <a-tooltip :title="r.status === 'active' ? '停用' : '启用'">
              <a-button size="small" type="text" @click="toggleStatus(r)">
                <template #icon><PoweroffOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip title="编辑">
              <a-button size="small" type="text" @click="openPlat(r)">
                <template #icon><EditOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip title="删除">
              <a-button size="small" type="text" danger @click="removeRule(r)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </a-tooltip>
          </div>
        </div>
        <button class="rr-add" @click="openPlat()">＋ 新增平台归置</button>
      </div>
      <div v-if="!filteredPlat.length" class="rr-none">
        {{ searchText ? '没有匹配的规则，换个关键词试试' : '还没有平台归置规则，点「＋ 新增平台归置」建一条' }}
      </div>
      </a-spin>
    </section>

    <!-- 大类二：场景配置基线 -->
    <section class="rr-sec">
      <div class="rr-sec-head">
        <span class="rr-sec-title">场景配置基线</span>
        <span class="rr-sec-count">{{ sceneCountLabel }}</span>
        <span class="rr-sec-desc">按场景给配置要点，AI 推荐时照基线校准数量与必备件</span>
      </div>
      <a-spin :spinning="loading">
      <div class="rr-grid">
        <div v-for="r in filteredScene" :key="r.id" class="rr-tile" :class="{ archived: r.status !== 'active' }" @click="openScene(r)">
          <div class="rr-t-top">
            <span class="rr-dot" :class="STATUS_META[r.status]?.cls" />
            <span class="rr-t-name">{{ r.name }}</span>
            <span v-if="r.status !== 'active'" class="rr-t-state">{{ STATUS_META[r.status]?.label }}</span>
          </div>
          <div class="rr-t-meta">
            <b>{{ itemsOf(r).length }} 条要点</b> · {{ itemsOf(r).map(i => i.category).join('/') }}
            <template v-if="r.hit_count"> · 命中 {{ r.hit_count }} 次</template>
          </div>
          <div class="rr-t-evi">{{ evidenceOf(r) }}</div>
          <div class="rr-t-foot" @click.stop>
            <a-tooltip :title="r.status === 'active' ? '停用' : '启用'">
              <a-button size="small" type="text" @click="toggleStatus(r)">
                <template #icon><PoweroffOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip title="编辑">
              <a-button size="small" type="text" @click="openScene(r)">
                <template #icon><EditOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip title="删除">
              <a-button size="small" type="text" danger @click="removeRule(r)">
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </a-tooltip>
          </div>
        </div>
        <button class="rr-add" @click="openScene()">＋ 新增场景基线</button>
      </div>
      <div v-if="!filteredScene.length" class="rr-none">
        {{ searchText ? '没有匹配的规则，换个关键词试试' : '还没有场景基线，点「＋ 新增场景基线」建一条' }}
      </div>
      </a-spin>
    </section>
      </div>
    </div>

  <!-- 弹窗：平台归置 -->
  <a-modal v-model:open="platOpen" :title="platTitle" :width="620" :footer="null">
    <div class="rr-m-body">
      <div class="rr-frow">
        <div class="rr-fld grow2">
          <label>名称 <i>*</i></label>
          <a-input v-model:value="platForm.name" placeholder="如：平台：CPU AMD/EPYC → Orion" />
        </div>
        <div class="rr-fld">
          <label>状态</label>
          <a-select v-model:value="platForm.status" :options="STATUS_OPTS" />
        </div>
      </div>
      <div class="rr-fld">
        <label>客户提到（命中任一信号词即适用） <i>*</i></label>
        <a-select v-model:value="platForm.signals" mode="tags" :token-separators="[',', '，']" placeholder="回车添加，如 AMD / EPYC / 霄龙" />
      </div>
      <div class="rr-frow">
        <div class="rr-fld">
          <label>推导平台 <i>*</i></label>
          <a-select v-model:value="platForm.platform" :options="platformOpts" placeholder="选择平台" />
        </div>
      </div>
      <div class="rr-fld">
        <label>依据 <i>*</i>（官方指南 / 参考架构 / 目录实测 / 业务确认）</label>
        <a-input v-model:value="platForm.evidence" placeholder="如：目录实测：Orion 在售机型 CPU 全为 EPYC" />
      </div>
      <div class="rr-tip">规则渲染进绑定节点的 AI 系统提示（知识注入）：AI 读词典按语义就近归置，另有影子校验在登记时比对；归置值属推断，须经客户确认。</div>
      <div class="rr-m-foot">
        <a-button @click="closeAll">取消</a-button>
        <a-button type="primary" @click="savePlat">保存</a-button>
      </div>
    </div>
  </a-modal>

  <!-- 弹窗：场景基线 -->
  <a-modal v-model:open="sceneOpen" :title="sceneTitle" :width="620" :footer="null">
    <div class="rr-m-body">
      <div class="rr-frow">
        <div class="rr-fld grow2">
          <label>名称 <i>*</i></label>
          <a-input v-model:value="sceneForm.name" placeholder="如：AI 训练服务器" />
        </div>
        <div class="rr-fld">
          <label>状态</label>
          <a-select v-model:value="sceneForm.status" :options="STATUS_OPTS" />
        </div>
      </div>
      <div class="rr-fld">
        <label>适用场景（客户需求命中信号词即适用） <i>*</i></label>
        <a-select v-model:value="sceneForm.signals" mode="tags" :token-separators="[',', '，']" placeholder="回车添加，如 训练 / GPU服务器 / 算力" />
      </div>
      <div class="rr-fld">
        <label>配置要点（类目 + 一句话要求） <i>*</i></label>
        <div v-for="(it, i) in sceneForm.items" :key="i" class="rr-item">
          <a-select v-model:value="it.category" :options="ITEM_CATS.map(c => ({ label: c, value: c }))" class="rr-item-cat" />
          <a-input v-model:value="it.text" placeholder="一句话要求，可带数量口径" />
          <button class="rr-item-x" @click="delItem(i)">✕</button>
        </div>
        <button class="rr-additem" @click="addItem">＋ 加一条要点</button>
      </div>
      <div class="rr-fld">
        <label>依据 <i>*</i>（官方指南 / 参考架构 / 目录实测 / 业务确认）</label>
        <a-input v-model:value="sceneForm.evidence" placeholder="如：NVIDIA 认证指南（内存≥2×显存、每 GPU ≥6 物理核）" />
      </div>
      <div class="rr-fld">
        <label>说明（可选）</label>
        <a-textarea v-model:value="sceneForm.desc" :rows="2" placeholder="如：训练内存 2×显存、推理 1×即可；客户明确给过数量时以客户为准。" />
      </div>
      <div class="rr-tip">基线只做推荐依据：AI 照此校准数量与必备件，客户明确给过数量时以客户为准。</div>
      <div class="rr-m-foot">
        <a-button @click="closeAll">取消</a-button>
        <a-button type="primary" @click="saveScene">保存</a-button>
      </div>
    </div>
  </a-modal>
  </div>
</template>

<style scoped>
.rrw { padding: 8px 24px 40px; }
.rr-bar {
  position: sticky; top: calc(var(--cpq-sticky-top, 0px) + 12px); z-index: 5;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 20px; border-radius: 12px;
  border: 1px solid var(--cpq-glass-border);
  box-shadow: var(--cpq-glass-card-shadow);
}
.rr-back { font-size: 13px; color: var(--cpq-text-secondary); cursor: pointer; white-space: nowrap; transition: color .18s; }
.rr-back:hover { color: var(--cpq-accent-primary); }
.rr-arrow { font-size: 14px; }
.rr-sep { color: var(--cpq-text-muted); opacity: .6; }
.rr-bar-title { font-size: 13.5px; font-weight: 600; color: var(--cpq-text-primary); }
.rr-tools { margin-left: auto; width: 240px; }
.rrw-body { margin-top: 16px; }
.rr-err {
  padding: 8px 14px; font-size: 12.5px; color: var(--cpq-accent-danger);
  border: 1px dashed rgba(255, 107, 107, .45); border-radius: 12px;
  background: rgba(255, 107, 107, .08);
}
.rr { display: flex; flex-direction: column; gap: 14px; }
.rr-head { display: flex; align-items: flex-start; gap: 16px; }
.rr-title { font-size: 21px; font-weight: 700; color: var(--cpq-text-primary); margin: 0; }
.rr-sub { font-size: 12.5px; color: var(--cpq-text-secondary); margin: 5px 0 0; }
.rr-sub em { font-style: normal; color: var(--cpq-accent-primary); }
.rr-scope {
  padding: 8px 14px; font-size: 12.5px; color: var(--cpq-text-secondary);
  border: 1px dashed rgba(22, 119, 255, .30); border-radius: 12px;
  background: rgba(22, 119, 255, .06);
}

.rr-sec { display: flex; flex-direction: column; gap: 12px; }
.rr-sec-head { display: flex; align-items: center; gap: 10px; }
.rr-sec-title { font-size: 15px; font-weight: 700; color: var(--cpq-text-primary); }
.rr-sec-count {
  font-size: 11.5px; color: var(--cpq-text-muted); padding: 0 8px;
  border-radius: 8px; background: var(--cpq-overlay-w6);
}
.rr-sec-desc { font-size: 12px; color: var(--cpq-text-muted); }

.rr-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.rr-tile {
  position: relative; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px;
  cursor: pointer; text-align: left; border: 1px solid var(--cpq-glass-border);
  border-radius: 14px; background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  transition: all .18s cubic-bezier(.16, 1, .3, 1);
}
.rr-tile:hover {
  border-color: var(--cpq-glass-border-strong); transform: translateY(-2px);
  box-shadow: var(--cpq-glass-card-shadow-hover);
}
.rr-tile.archived { opacity: .55; }
.rr-t-top { display: flex; align-items: center; gap: 7px; min-width: 0; }
.rr-dot { width: 6px; height: 6px; border-radius: 50%; flex: none; background: var(--cpq-text-muted); }
.rr-dot.on { background: var(--cpq-color-success); box-shadow: 0 0 0 3px rgba(82, 201, 160, .22); }
.rr-dot.warn { background: var(--cpq-color-warning); }
.rr-dot.info { background: var(--cpq-accent-primary); }
.rr-dot.off { background: var(--cpq-text-muted); }
.rr-t-name {
  font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rr-t-meta { font-size: 11.5px; color: var(--cpq-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rr-t-meta b { color: var(--cpq-text-secondary); font-weight: 600; }
.rr-t-evi {
  font-size: 11px; color: var(--cpq-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding-top: 4px; border-top: 1px dashed var(--cpq-glass-border);
}
.rr-t-evi::before { content: '依据：'; color: var(--cpq-text-muted); }
.rr-t-state {
  flex: none; font-size: 10.5px; line-height: 1; padding: 3px 7px;
  border-radius: 8px; color: var(--cpq-color-warning);
  background: rgba(250, 173, 20, .14);
}
.rr-t-foot {
  display: flex; gap: 2px; justify-content: flex-end;
  margin: 2px -6px -6px; padding-top: 2px;
  border-top: 1px dashed var(--cpq-glass-border);
}
.rr-t-foot :deep(.ant-btn) { color: var(--cpq-text-muted); }
.rr-t-foot :deep(.ant-btn:hover) { color: var(--cpq-accent-primary); }
.rr-t-foot :deep(.ant-btn-dangerous:hover) { color: var(--cpq-accent-danger) !important; }

.rr-add {
  border: 1px dashed var(--cpq-glass-border); border-radius: 14px; min-height: 74px;
  display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted);
  font-size: 12.5px; cursor: pointer; background: transparent; transition: .18s;
}
.rr-add:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-accent-primary); }

.rr-none {
  margin-top: 10px; padding: 14px; text-align: center; font-size: 12.5px;
  color: var(--cpq-text-muted); border: 1px dashed var(--cpq-glass-border); border-radius: 14px;
}

.rr-m-body { display: flex; flex-direction: column; gap: 13px; padding-top: 4px; }
.rr-frow { display: flex; gap: 12px; }
.rr-fld { flex: 1; display: flex; flex-direction: column; gap: 5px; }
.rr-fld.grow2 { flex: 2; }
.rr-fld label { font-size: 12px; color: var(--cpq-text-secondary); }
.rr-fld label i { color: var(--cpq-accent-danger); font-style: normal; margin-left: 2px; }
.rr-item { display: grid; grid-template-columns: 120px 1fr 28px; gap: 8px; align-items: center; }
.rr-item + .rr-item { margin-top: 8px; }
.rr-item-cat { width: 120px; }
.rr-item-x { border: 0; background: transparent; color: var(--cpq-text-muted); cursor: pointer; font-size: 14px; }
.rr-item-x:hover { color: var(--cpq-accent-danger); }
.rr-additem {
  margin-top: 9px; border: 1px dashed var(--cpq-glass-border); background: transparent;
  color: var(--cpq-text-secondary); font-size: 12px; padding: 5px 10px;
  border-radius: 8px; cursor: pointer; width: 100%; transition: .18s;
}
.rr-additem:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-accent-primary); }
.rr-tip { font-size: 11px; color: var(--cpq-text-muted); }
.rr-m-foot { display: flex; justify-content: flex-end; gap: 10px; padding-top: 4px; }
</style>


