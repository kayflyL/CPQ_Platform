<script setup lang="ts">
/** 服务器3D模型 · 模型页(独立路由 /servers/3d-models/:id)。
 *  页内全屏3D(顶栏融合,非浏览器全屏):左上=返回+模型信息,右上=管理浮窗
 *  (名称/关联机型多选——绑定即上架/分区标注自定义,改动实时反映到画布提示)。
 *  删除入口在目录页(带二次确认),本页不设。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, UpOutlined } from '@ant-design/icons-vue'
import { server3dApi, type Server3dModel } from '@/api/server3d'
import { catalogApi, type ServerModel } from '@/api/serverConfig'
import ServerStage3D from '@/components/server-3d/ServerStage3D.vue'
import { PART_INFO } from '@/server3d/machine'
import { REGION_SLOT_TYPES, PART_TYPE_LABELS } from '@/server3d/partRegistry'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const loading = ref(false)
const saving = ref(false)
const name = ref('')
const modelIds = ref<number[]>([])
/** 部件模型(kind='part'):独立预览,不参与机型绑定与分区标注覆盖 */
const isPart = ref(false)
/** 部件类型:注册表内可选(有工厂能渲染的才在列);stage 侧仅认注册表键 */
const partType = ref<string | null>(null)
const partTypeOptions = Object.entries(PART_TYPE_LABELS).map(([value, label]) => ({ value, label }))
const stagePartType = computed(() => (partType.value && partType.value in PART_TYPE_LABELS ? (partType.value as 'cpu' | 'fan') : null))
const partSpec = ref<{ family?: 'sp5' | 'kh' } | null>(null)
/** 分区标注覆盖:仅记录用户填过的字段 */
const labelForm = ref<Record<string, { name: string; spec: string; desc: string }>>({})
const labelsOpen = ref(true)
const serverModels = ref<ServerModel[]>([])
/* ── 分区绑定(整机行):分区即部件槽位,绑定权在服务器模型行,部件行=纯资产登记 ── */
const rawLc = ref<Record<string, any>>({})
const partRows = ref<Server3dModel[]>([])
/** 分区→部件行绑定表(machine.bindings),键=分区键(cpu/fans/…),值=部件库行id */
const bindings = ref<Record<string, number | null>>({})
/** 某分区可绑的部件行(按槽位类型过滤);部件库无该类部件时分区不出绑定下拉 */
function slotRows(regionKey: string): Server3dModel[] {
  const t = REGION_SLOT_TYPES[regionKey]
  return t ? partRows.value.filter((p: Server3dModel) => p.part_type === t) : []
}
/** 部件行形态族(部件行 layout_config.family);未绑定=undefined→默认 AMD */
function partFamily(pid: number | null | undefined): 'sp5' | 'kh' | undefined {
  if (pid == null) return undefined
  const row = partRows.value.find((p: Server3dModel) => p.id === pid)
  try {
    const f = row?.layout_config ? JSON.parse(row.layout_config)?.family : undefined
    return f === 'kh' || f === 'sp5' ? f : undefined
  } catch { return undefined }
}
/** 画布预览的处理器形态(=CPU 分区绑定行的形态族;未绑定→默认 AMD) */
const cpuFamilyResolved = computed<'sp5' | 'kh' | undefined>(() => partFamily(bindings.value.cpu))

const PART_KEYS = Object.entries(PART_INFO).map(([key, v]) => ({ key, def: v.name, defSpec: v.spec, defDesc: v.desc }))

const modelOptions = computed(() => serverModels.value.map(m => ({ value: m.id, label: m.name })))
const boundNames = computed(() => modelIds.value.map(mid => serverModels.value.find(m => m.id === mid)?.name || `机型#${mid}`))

/** layout_config 合并保存:labels + machine(cpu_part_id)并入原始 lc,未知键保留 */
const layoutConfig = computed(() => {
  const labels: Record<string, { name: string; spec: string; desc: string }> = {}
  for (const [k, v] of Object.entries(labelForm.value)) {
    if (!v) continue
    labels[k] = { name: v.name.trim(), spec: v.spec.trim(), desc: v.desc.trim() }
  }
  const out: Record<string, unknown> = { ...(rawLc.value || {}) }
  if (Object.keys(labels).length) out.labels = labels
  else delete out.labels
  const cleanBindings = Object.fromEntries(Object.entries(bindings.value).filter(([, v]) => v != null))
  if (Object.keys(cleanBindings).length) out.machine = { ...((out.machine as any) || {}), bindings: cleanBindings }
  else if (out.machine) {
    const mm = { ...((out.machine as any) || {}) }
    delete mm.bindings
    if (!Object.keys(mm).length) delete out.machine
  }
  return Object.keys(out).length ? JSON.stringify(out) : null
})
/** 预览用标注(草稿态即生效) */
const previewLabels = computed(() => {
  const out: Record<string, { name?: string; spec?: string; desc?: string }> = {}
  for (const [k, v] of Object.entries(labelForm.value)) {
    if (!v) continue
    out[k] = { name: v.name.trim(), spec: v.spec.trim(), desc: v.desc.trim() }
  }
  return Object.keys(out).length ? out : undefined
})

async function load() {
  loading.value = true
  try {
    const list = await server3dApi.list()
    const m = list.find(x => x.id === id.value)
    if (!m) {
      message.error('3D模型不存在')
      router.replace('/servers/admin?refresh=model3d')
      return
    }
    name.value = m.name
    modelIds.value = [...(m.model_ids || [])]
    isPart.value = m.kind === 'part'
    partType.value = m.kind === 'part' ? (m.part_type ?? null) : null
    try {
      const lc = m.layout_config ? JSON.parse(m.layout_config) : null
      partSpec.value = lc?.family ? { family: lc.family } : null
      rawLc.value = lc || {}
      partRows.value = list.filter(x => x.kind === 'part')
      const b: Record<string, unknown> = lc?.machine?.bindings || {}
      bindings.value = Object.fromEntries(
        Object.entries(b).filter(([, v]) => v != null).map(([k, v]) => [k, Number(v)]),
      )
      const lf: Record<string, { name: string; spec: string; desc: string }> = {}
      for (const { key, def, defSpec, defDesc } of PART_KEYS) {
        const o = lc?.labels?.[key] || {}
        // 预填生效文案(已存覆盖否则默认),用户一眼对上号
        lf[key] = { name: o.name || def, spec: o.spec || defSpec, desc: o.desc || defDesc }
      }
      labelForm.value = lf
    } catch { labelForm.value = {} }
    const res = await catalogApi.listModels().catch(() => ({ models: [] as ServerModel[] }))
    serverModels.value = (res as any).models || []
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function setLabel(key: string, field: 'name' | 'spec' | 'desc', v: string) {
  const cur = labelForm.value[key] || { name: '', spec: '', desc: '' }
  cur[field] = v
  labelForm.value[key] = cur
}
function resetLabel(key: string) {
  const p = PART_KEYS.find(x => x.key === key)
  if (!p) return
  labelForm.value[key] = { name: p.def, spec: p.defSpec, desc: p.defDesc }
}

async function save() {
  if (!name.value.trim()) return message.warning('请填写模型名称')
  saving.value = true
  try {
    // 部件模型:改名+部件类型(layout_config 形态族不触碰,由部件蓝图定调)
    await server3dApi.update(id.value, isPart.value
      ? { name: name.value.trim(), part_type: partType.value || undefined, model_ids: [] }
      : {
          name: name.value.trim(),
          model_ids: modelIds.value,
          layout_config: layoutConfig.value,
        })
    message.success(isPart.value ? '已保存' : boundNames.value.length ? `已保存,${boundNames.value.length} 台机型配置页将显示该3D场景` : '已保存(未关联机型,配置页暂不显示)')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function back() {
  router.push('/servers/admin?refresh=model3d')
}

/* ── 复制(分裂):当前行整份登记复制出新行,绑定清空不上架,配置/文案留原样供改 ── */
const copying = ref(false)
async function copyModel() {
  copying.value = true
  try {
    const res = await server3dApi.create({
      name: `${name.value.trim() || '未命名'} · 副本`,
      kind: isPart.value ? 'part' : 'machine',
      part_type: partType.value,
      layout_config: layoutConfig.value,
      model_ids: [],
    })
    message.success('已复制出新模型行(未关联机型),正在打开副本')
    await router.replace(`/servers/3d-models/${res.model.id}`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '复制失败')
  } finally {
    copying.value = false
  }
}

/* 顶栏融合:深色主题时声明 hero-dark,顶栏透明浅字压在画布上(同服务器目录banner) */
const pageTheme = () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
function syncHeroDark() {
  if (pageTheme() === 'dark') document.documentElement.dataset.heroDark = '1'
  else delete document.documentElement.dataset.heroDark
}
const themeMo = new MutationObserver(syncHeroDark)
onMounted(() => {
  load()
  syncHeroDark()
  themeMo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})
onBeforeUnmount(() => {
  themeMo.disconnect()
  delete document.documentElement.dataset.heroDark
})

// 预览=默认满配(8GPU/2CPU/24内存/12盘位)
const previewCounts = { gpus: 8, cpus: 2, dimms: 24, bays: 12 }
</script>

<template>
  <div class="s3de-root">
    <div class="s3de-stage">
      <ServerStage3D
        v-if="!isPart" :counts="previewCounts" :labels="previewLabels" :cpu-family="cpuFamilyResolved" class="s3de-stage3d" height="100%"
      />
      <ServerStage3D
        v-else :part-type="stagePartType" :part-spec="partSpec" class="s3de-stage3d" height="100%"
      />

      <!-- 左上:返回 + 模型信息 -->
      <div class="s3de-hud s3de-hud-tl">
        <button type="button" class="s3de-back" @click="back">
          <ArrowLeftOutlined />
          <span>返回目录</span>
        </button>
        <div class="s3de-hud-name">{{ name || '未命名3D模型' }}</div>
        <div class="s3de-hud-sub">
          <template v-if="isPart">部件模型 · {{ PART_TYPE_LABELS[partType || ''] || partType || '?' }}</template>
          <template v-else-if="boundNames.length">
            关联机型 · <b>{{ boundNames[0] }}</b><span v-if="boundNames.length > 1"> 等 {{ boundNames.length }} 台</span>
          </template>
          <template v-else>未关联机型(配置页不显示)</template>
        </div>
      </div>

      <!-- 右上:管理浮窗 -->
      <div class="s3de-hud s3de-hud-tr">
        <div class="s3de-hud-title">管理</div>
        <div class="s3de-field">
          <label class="s3de-label">模型名称</label>
          <a-input v-model:value="name" placeholder="如:4U8卡服务器模型" @pressEnter="save" />
        </div>
        <div class="s3de-field" v-if="!isPart">
          <label class="s3de-label">关联机型(可多选,绑定即上架)</label>
          <a-select
            v-model:value="modelIds"
            mode="multiple"
            :options="modelOptions"
            placeholder="选择服务器产品机型"
            allow-clear
            show-search
            option-filter-prop="label"
            :max-tag-count="3"
          />
        </div>
        <div class="s3de-field" v-if="isPart">
          <label class="s3de-label">部件类型(决定画布用哪个部件工厂渲染)</label>
          <a-select v-model:value="partType" :options="partTypeOptions" placeholder="选择部件类型" />
        </div>

        <div class="s3de-lsec" v-if="!isPart">
          <div class="s3de-lsec-head" @click="labelsOpen = !labelsOpen">
            <span>分区标注 · 悬停提示文案</span>
            <UpOutlined class="s3de-chev" :class="{ open: labelsOpen }" />
          </div>
          <div v-show="labelsOpen" class="s3de-lbody">
            <div v-for="(p, idx) in PART_KEYS" :key="p.key" class="s3de-lgroup">
              <div class="s3de-lgroup-head">
                <span class="s3de-lidx">{{ idx + 1 }}</span>
                <span class="s3de-ldef" :title="p.def">{{ p.def }}</span>
                <button type="button" class="s3de-lreset" @click="resetLabel(p.key)">重置</button>
              </div>
              <div class="s3de-lrow" v-if="slotRows(p.key).length">
                <span class="s3de-ltag">绑定</span>
                <a-select
                  :value="bindings[p.key] ?? null"
                  :options="[
                    { value: null, label: '不绑定(默认形态)' },
                    ...slotRows(p.key).map(r => ({ value: r.id, label: r.name })),
                  ]"
                  size="small"
                  allow-clear
                  @update:value="(v: any) => { bindings[p.key] = v ?? null }"
                />
              </div>
              <div class="s3de-lrow">
                <span class="s3de-ltag">名称</span>
                <a-input
                  :value="labelForm[p.key]?.name || ''"
                  size="small"
                  @update:value="(v: any) => setLabel(p.key, 'name', v)"
                />
              </div>
              <div class="s3de-lrow">
                <span class="s3de-ltag">规格</span>
                <a-input
                  :value="labelForm[p.key]?.spec || ''"
                  size="small"
                  @update:value="(v: any) => setLabel(p.key, 'spec', v)"
                />
              </div>
              <div class="s3de-lrow">
                <span class="s3de-ltag">说明</span>
                <a-textarea
                  :value="labelForm[p.key]?.desc || ''"
                  :auto-size="{ minRows: 1, maxRows: 3 }"
                  size="small"
                  @update:value="(v: any) => setLabel(p.key, 'desc', v)"
                />
              </div>
            </div>
            <p class="s3de-hint">改动即时反映到画布悬停提示;「重置」恢复默认文案,保存后持久化。</p>
          </div>
        </div>

        <div class="s3de-ops">
          <a-button v-if="!isPart" block :loading="copying" @click="copyModel">复制此模型(分裂新行)</a-button>
          <a-button type="primary" block :loading="saving" @click="save">保存</a-button>
        </div>
        <p class="s3de-hint" v-if="!isPart">复制 = 整份登记分裂出新行:绑定清空不上架,组装配置与悬停文案留原样供改。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.s3de-root {
  /* 顶栏融合:负margin垫到透明顶栏下(同服务器目录banner),画布从视口顶铺起 */
  position: relative;
  margin-top: calc(-1 * var(--cpq-header-clearance, 64px));
  height: calc(100vh - var(--cpq-space-4));
  min-height: 520px;
}
.s3de-stage {
  position: relative;
  height: 100%;
  overflow: hidden;
}
.s3de-stage3d {
  height: 100%;
}
.s3de-hud {
  position: absolute;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-3);
  padding: var(--cpq-space-4) var(--cpq-space-5);
  background: var(--cpq-overlay-b40);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-md);
  backdrop-filter: blur(12px);
}
.s3de-hud-tl {
  top: calc(var(--cpq-header-clearance, 64px) + var(--cpq-space-4));
  left: var(--cpq-space-5);
  min-width: 240px;
}
.s3de-hud-tr {
  top: calc(var(--cpq-header-clearance, 64px) + var(--cpq-space-4));
  right: var(--cpq-space-5);
  width: 288px;
  max-height: calc(100vh - var(--cpq-header-clearance, 64px) - var(--cpq-space-6));
  overflow-y: auto;
}
.s3de-back {
  appearance: none;
  display: inline-flex;
  align-items: center;
  gap: var(--cpq-space-1);
  align-self: flex-start;
  border: 1px solid var(--cpq-overlay-w10);
  background: var(--cpq-overlay-b20);
  color: var(--cpq-text-primary);
  font-size: var(--cpq-font-size-xs);
  padding: 2px 10px;
  border-radius: var(--cpq-radius-full);
  cursor: pointer;
  transition: border-color 0.18s ease;
}
.s3de-back:hover {
  border-color: var(--cpq-accent-primary);
}
.s3de-hud-name {
  font-size: var(--cpq-font-size-xl);
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--cpq-text-primary);
  line-height: 1.25;
}
.s3de-hud-sub {
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-sm);
}
.s3de-hud-sub b {
  color: var(--cpq-accent-primary);
  font-weight: 600;
}
.s3de-hud-title {
  font-size: var(--cpq-font-size-sm);
  font-weight: 700;
  color: var(--cpq-text-primary);
}
.s3de-field {
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-1);
}
.s3de-label {
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-xs);
}
/* 分区标注:分组小节(组头=序号+默认名+重置),行内小标签,说明用自适应文本域 */
.s3de-lsec {
  border-top: 1px solid var(--cpq-overlay-w10);
  padding-top: var(--cpq-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-2);
}
.s3de-lsec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-xs);
}
.s3de-chev {
  font-size: 10px;
  transition: transform 0.2s ease;
}
.s3de-chev.open {
  transform: rotate(180deg);
}
.s3de-lbody {
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-3);
}
.s3de-lgroup {
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-1);
  padding-bottom: var(--cpq-space-2);
  border-bottom: 1px dashed var(--cpq-overlay-w10);
}
.s3de-lgroup:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.s3de-lgroup-head {
  display: flex;
  align-items: center;
  gap: var(--cpq-space-2);
  margin-bottom: 2px;
}
.s3de-lidx {
  min-width: 14px;
  text-align: center;
  color: var(--cpq-text-muted);
  font-size: var(--cpq-font-size-xs);
  line-height: 1;
}
.s3de-ldef {
  flex: 1;
  min-width: 0;
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.s3de-lreset {
  appearance: none;
  border: none;
  background: none;
  padding: 0;
  color: var(--cpq-text-muted);
  font-size: var(--cpq-font-size-xs);
  cursor: pointer;
}
.s3de-lreset:hover {
  color: var(--cpq-accent-primary);
}
.s3de-lrow {
  display: flex;
  align-items: flex-start;
  gap: var(--cpq-space-1);
}
.s3de-ltag {
  width: 30px;
  flex-shrink: 0;
  padding-top: 4px;
  color: var(--cpq-text-muted);
  font-size: var(--cpq-font-size-xs);
  line-height: 1.3;
}
.s3de-hint {
  margin: 0;
  color: var(--cpq-text-muted);
  font-size: var(--cpq-font-size-xs);
}
.s3de-ops {
  border-top: 1px solid var(--cpq-overlay-w10);
  padding-top: var(--cpq-space-3);
  margin-top: var(--cpq-space-1);
}
/* 玻璃底上的字段层次:可填区域做出底/边区分,focus 走主题色 */
.s3de-hud-tr :deep(.ant-input),
.s3de-hud-tr :deep(.ant-input-affix-wrapper),
.s3de-hud-tr :deep(.ant-select-selector) {
  background: var(--cpq-overlay-b20);
  border-color: var(--cpq-overlay-w10);
}
.s3de-hud-tr :deep(.ant-input:focus),
.s3de-hud-tr :deep(.ant-input-focused),
.s3de-hud-tr :deep(.ant-input-affix-wrapper-focused),
.s3de-hud-tr :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--cpq-accent-primary) 16%, transparent) !important;
}
@media (max-width: 760px) {
  .s3de-root {
    margin-top: 0;
    height: auto;
    min-height: 60vh;
  }
  .s3de-stage {
    min-height: 60vh;
  }
  .s3de-hud-tl,
  .s3de-hud-tr {
    top: var(--cpq-space-2);
    left: var(--cpq-space-2);
    right: var(--cpq-space-2);
  }
  .s3de-hud-tr {
    left: auto;
  }
}
</style>
