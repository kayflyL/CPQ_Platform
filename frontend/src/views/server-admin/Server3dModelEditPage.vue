<script setup lang="ts">
/** 服务器3D模型 · 模型页(独立路由 /servers/3d-models/:id)。
 *  页内全屏3D(顶栏融合,非浏览器全屏):左上=返回+模型信息,右上=管理浮窗
 *  (名称/关联机型多选——绑定即上架/分区标注自定义,改动实时反映到画布提示)。
 *  删除入口在目录页(带二次确认),本页不设。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, UpOutlined } from '@ant-design/icons-vue'
import { server3dApi } from '@/api/server3d'
import { catalogApi, type ServerModel } from '@/api/serverConfig'
import ServerStage3D from '@/components/server-3d/ServerStage3D.vue'
import { PART_INFO } from '@/server3d/machine'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const loading = ref(false)
const saving = ref(false)
const name = ref('')
const modelIds = ref<number[]>([])
/** 分区标注覆盖:仅记录用户填过的字段 */
const labelForm = ref<Record<string, { name: string; spec: string; desc: string }>>({})
const labelsOpen = ref(true)
const serverModels = ref<ServerModel[]>([])

const PART_KEYS = Object.entries(PART_INFO).map(([key, v]) => ({ key, def: v.name, defSpec: v.spec, defDesc: v.desc }))

const modelOptions = computed(() => serverModels.value.map(m => ({ value: m.id, label: m.name })))
const boundNames = computed(() => modelIds.value.map(mid => serverModels.value.find(m => m.id === mid)?.name || `机型#${mid}`))

/** 分区标注 → layout_config.labels(三行全存,画布渲染即所见) */
const layoutConfig = computed(() => {
  const labels: Record<string, { name: string; spec: string; desc: string }> = {}
  for (const [k, v] of Object.entries(labelForm.value)) {
    if (!v) continue
    labels[k] = { name: v.name.trim(), spec: v.spec.trim(), desc: v.desc.trim() }
  }
  return Object.keys(labels).length ? JSON.stringify({ labels }) : null
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
    try {
      const lc = m.layout_config ? JSON.parse(m.layout_config) : null
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
    await server3dApi.update(id.value, {
      name: name.value.trim(),
      model_ids: modelIds.value,
      layout_config: layoutConfig.value,
    })
    message.success(boundNames.value.length ? `已保存,${boundNames.value.length} 台机型配置页将显示该3D场景` : '已保存(未关联机型,配置页暂不显示)')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function back() {
  router.push('/servers/admin?refresh=model3d')
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
      <ServerStage3D :counts="previewCounts" :labels="previewLabels" class="s3de-stage3d" height="100%" />

      <!-- 左上:返回 + 模型信息 -->
      <div class="s3de-hud s3de-hud-tl">
        <button type="button" class="s3de-back" @click="back">
          <ArrowLeftOutlined />
          <span>返回目录</span>
        </button>
        <div class="s3de-hud-name">{{ name || '未命名3D模型' }}</div>
        <div class="s3de-hud-sub">
          <template v-if="boundNames.length">
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
        <div class="s3de-field">
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

        <div class="s3de-lsec">
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
          <a-button type="primary" block :loading="saving" @click="save">保存</a-button>
        </div>
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
