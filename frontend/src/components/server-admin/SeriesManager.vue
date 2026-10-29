<script setup lang="ts">
/** 产品系列管理 — 管理服务器类型及其 3D 展示配置。
 *  列表 + 编辑弹窗（基础信息 + 展示内容 + 渲染参数）。
 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import type { ShowcaseConfig } from '@/components/server-config/showcase-config'
import { catalogApi } from '@/api/serverConfig'
import RenderConfigEditor from './RenderConfigEditor.vue'
import ShowcasePreview from './ShowcasePreview.vue'

interface ServerType {
  id: number
  name: string
  description?: string
  sort_order?: number
  showcase_config?: ShowcaseConfig
}

const loading = ref(false)
const types = ref<ServerType[]>([])
const modalVisible = ref(false)
const editId = ref<number | null>(null)
const editForm = ref<Partial<ServerType>>({})
const editTab = ref<'basic' | 'showcase' | 'render'>('basic')
const saving = ref(false)
const activeCollapse = ref<string[]>([]) // 默认全部折叠

// 默认渲染配置
const defaultRenderConfig = {
  light: {
    ambient_intensity: 0.6,
    key_light_intensity: 1.45,
    fill_light_intensity: 0.35,
    key_light_color: '#ffffff',
    fill_light_color: '#bfd4ff',
    background_color: '#000000',
    tone_mapping: 'NoToneMapping' as const,
    exposure: 1.0,
  },
  dark: {
    ambient_intensity: 0.9,
    key_light_intensity: 1.1,
    fill_light_intensity: 0.5,
    key_light_color: '#ffffff',
    fill_light_color: '#bfd4ff',
    background_color: '#000000',
    tone_mapping: 'NoToneMapping' as const,
    exposure: 1.0,
  },
  camera_fov: 45,
  auto_rotate_speed: 0.8,
  enable_damping: true,
  damping_factor: 0.08,
}

async function load() {
  loading.value = true
  try {
    const res = await catalogApi.listTypes()
    types.value = res.types
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  editForm.value = {
    showcase_config: {
      glb_path: null,
      title: '',
      description: '',
      bullets: [],
      render: JSON.parse(JSON.stringify(defaultRenderConfig)),
    },
  }
  editTab.value = 'basic'
  modalVisible.value = true
}

function openEdit(t: ServerType) {
  editId.value = t.id
  const renderConfig = t.showcase_config?.render
    ? JSON.parse(JSON.stringify(t.showcase_config.render))
    : JSON.parse(JSON.stringify(defaultRenderConfig))

  editForm.value = {
    ...t,
    showcase_config: {
      glb_path: t.showcase_config?.glb_path || null,
      title: t.showcase_config?.title || '',
      description: t.showcase_config?.description || '',
      bullets: t.showcase_config?.bullets || [],
      render: renderConfig,
    },
  }
  editTab.value = 'basic'
  modalVisible.value = true
}

async function save() {
  if (!editForm.value.name) {
    message.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    if (editId.value) {
      await catalogApi.updateType(editId.value, editForm.value)
      message.success('更新成功')
    } else {
      await catalogApi.createType(editForm.value)
      message.success('创建成功')
    }
    modalVisible.value = false
    load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function removeBullet(idx: number) {
  if (editForm.value.showcase_config?.bullets) {
    editForm.value.showcase_config.bullets.splice(idx, 1)
  }
}

function addBullet() {
  if (!editForm.value.showcase_config) {
    editForm.value.showcase_config = { glb_path: null, title: '', description: '', bullets: [] }
  }
  if (!editForm.value.showcase_config.bullets) {
    editForm.value.showcase_config.bullets = []
  }
  editForm.value.showcase_config.bullets.push('')
}

/** 卡片按管理排序（sort_order）升序展示 */
const sortedTypes = computed(() =>
  [...types.value].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
)

onMounted(load)
</script>

<template>
  <div class="series-manager">
      <div class="panel-head">
        <h2>产品系列</h2>
        <a-button type="primary" @click="openCreate">+ 新建系列</a-button>
      </div>
      <a-spin :spinning="loading">
        <div v-if="sortedTypes.length" class="sm-list">
          <div v-for="t in sortedTypes" :key="t.id" class="sm-card glass-light">
            <div class="sr-thumb">
              <span v-if="t.showcase_config?.glb_path" class="glb-tag">GLB</span>
              <span v-else class="glb-tag glb-empty">未配置</span>
            </div>
            <div class="sr-main">
              <div class="sr-name">{{ t.name }}</div>
              <div class="sr-desc">{{ t.description || '暂无描述' }}</div>
            </div>
            <div class="sr-side">
              <span :class="['chip3d', t.showcase_config?.glb_path ? 'on' : 'off']">
                {{ t.showcase_config?.glb_path ? '已配 3D 展示' : '未配置展示' }}
              </span>
              <a-button @click="openEdit(t)">编辑</a-button>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无系列，点「+ 新建系列」添加" />
      </a-spin>

    <!-- 编辑弹窗 -->
    <a-modal
      :open="modalVisible"
      :title="editId ? '编辑产品系列' : '新建产品系列'"
      @ok="save"
      @cancel="modalVisible = false"
      width="960px"
      :destroyOnClose="true"
    >
      <a-tabs v-model:activeKey="editTab">
        <!-- 基础信息 Tab -->
        <a-tab-pane key="basic" tab="基础信息">
          <a-form layout="vertical">
            <a-form-item label="名称" required>
              <a-input v-model:value="editForm.name" placeholder="如：AI 加速计算服务器" />
            </a-form-item>
            <a-form-item label="描述">
              <a-textarea
                v-model:value="editForm.description"
                placeholder="模型训练与推理，多 GPU"
                :rows="3"
              />
            </a-form-item>
            <a-form-item label="排序">
              <a-input-number v-model:value="editForm.sort_order" :min="0" />
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <!-- 展示内容 Tab -->
        <a-tab-pane key="showcase" tab="展示内容">
          <a-form layout="vertical">
            <a-form-item label="GLB 模型">
              <a-input
                v-model:value="editForm.showcase_config!.glb_path"
                placeholder="/models/ai-server.glb"
              />
              <div class="field-hint">模型路径（上传后自动填充）</div>
            </a-form-item>
            <a-form-item label="标题">
              <a-input v-model:value="editForm.showcase_config!.title" />
            </a-form-item>
            <a-form-item label="描述">
              <a-textarea v-model:value="editForm.showcase_config!.description" :rows="3" />
            </a-form-item>
            <a-form-item label="要点列表">
              <div v-for="(b, i) in editForm.showcase_config?.bullets" :key="i" class="bullet-row">
                <a-input :value="b" @update:value="(v: string) => editForm.showcase_config!.bullets[i] = v" />
                <a-button link danger size="small" @click="removeBullet(i)">删除</a-button>
              </div>
              <a-button link size="small" @click="addBullet">+ 添加要点</a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>

        <!-- 渲染参数 Tab -->
        <a-tab-pane key="render" tab="渲染参数">
          <div class="render-layout">
            <!-- 实时预览（占满整个区域）-->
            <div class="render-preview">
              <div v-if="!editForm.showcase_config?.glb_path" class="preview-placeholder">
                <span>请先上传 GLB 模型文件</span>
              </div>
              <!-- 只在 tab 激活且有 GLB 路径时渲染 -->
              <ShowcasePreview
                v-else-if="editTab === 'render'"
                :config="editForm.showcase_config"
              />
            </div>

            <!-- 浮动参数面板 -->
            <div v-if="editForm.showcase_config?.glb_path" class="render-params-overlay">
              <a-collapse v-model:activeKey="activeCollapse" ghost>
                <!-- 浅色主题 -->
                <a-collapse-panel key="light" header="浅色主题">
                  <RenderConfigEditor
                    v-if="editForm.showcase_config?.render?.light"
                    :config="editForm.showcase_config.render.light"
                    theme="light"
                    @update:config="editForm.showcase_config!.render!.light = $event"
                  />
                </a-collapse-panel>

                <!-- 深色主题 -->
                <a-collapse-panel key="dark" header="深色主题">
                  <RenderConfigEditor
                    v-if="editForm.showcase_config?.render?.dark"
                    :config="editForm.showcase_config.render.dark"
                    theme="dark"
                    @update:config="editForm.showcase_config!.render!.dark = $event"
                  />
                </a-collapse-panel>

                <!-- 相机与控制 -->
                <a-collapse-panel key="camera" header="相机与控制">
                  <div class="camera-controls">
                    <div class="field-row">
                      <label>相机 FOV</label>
                      <a-input-number
                        v-model:value="editForm.showcase_config!.render!.camera_fov"
                        :min="30"
                        :max="90"
                        :step="5"
                        style="width: 100px"
                      />
                    </div>
                    <div class="field-row">
                      <label>自动旋转速度</label>
                      <a-input-number
                        v-model:value="editForm.showcase_config!.render!.auto_rotate_speed"
                        :min="0"
                        :max="2"
                        :step="0.1"
                        style="width: 100px"
                      />
                    </div>
                    <div class="field-row">
                      <label>启用阻尼</label>
                      <a-switch v-model:checked="editForm.showcase_config!.render!.enable_damping" />
                    </div>
                    <div class="field-row">
                      <label>阻尼因子</label>
                      <a-input-number
                        v-model:value="editForm.showcase_config!.render!.damping_factor"
                        :min="0"
                        :max="0.5"
                        :step="0.01"
                        :precision="2"
                        style="width: 100px"
                      />
                    </div>
                  </div>
                </a-collapse-panel>
              </a-collapse>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-modal>
  </div>
</template>

<style scoped>
.series-manager { margin-bottom: 18px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.panel-head h2 { margin: 0; font-size: 17px; font-weight: 700; }
.sm-list { display: flex; flex-direction: column; gap: 12px; }
.sm-card { display: flex; align-items: center; gap: 16px; padding: 14px 16px; }
.sr-thumb {
  width: 120px; height: 76px; border-radius: var(--cpq-radius-md); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(145deg, var(--cpq-overlay-a8), var(--cpq-overlay-a4));
  border: 1px solid var(--cpq-glass-border);
}
.glb-tag {
  font-size: var(--cpq-font-size-xs); letter-spacing: 2px; padding: 4px 10px;
  color: var(--cpq-text-secondary);
  border: 1px dashed var(--cpq-glass-border); border-radius: var(--cpq-radius-sm);
}
.glb-tag.glb-empty { color: var(--cpq-text-disabled); }
.sr-main { flex: 1; min-width: 0; }
.sr-name { font-size: 15px; font-weight: 700; color: var(--cpq-text-primary); }
.sr-desc { font-size: 12.5px; color: var(--cpq-text-secondary); margin-top: 4px; }
.sr-side { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.chip3d { font-size: var(--cpq-font-size-sm); padding: 3px 10px; border-radius: var(--cpq-radius-full); white-space: nowrap; }
.chip3d.on { color: var(--cpq-color-success); background: var(--cpq-overlay-success15); }
.chip3d.off { color: var(--cpq-text-muted); background: var(--cpq-overlay-w5); border: 1px solid var(--cpq-glass-border); }
@media (max-width: 768px) {
  .sm-card { flex-wrap: wrap; }
  .sr-side { width: 100%; justify-content: flex-end; }
}
.bullet-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.bullet-row .ant-input {
  flex: 1;
}
.field-hint {
  font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-muted, #6E7582);
  margin-top: 4px;
}
.camera-controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.camera-controls .field-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.camera-controls .field-row label {
  width: 120px;
  font-size: 13px;
}

/* 渲染参数布局：预览占满，参数面板浮动 */
.render-layout {
  position: relative;
  min-height: 500px;
  height: 70vh;
}

.render-preview {
  position: absolute;
  inset: 0;
  border-radius: var(--cpq-radius-md);
  overflow: hidden;
  background: var(--cpq-overlay-b20);
  border: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.08));
}

/* 浮动参数面板 - 毛玻璃效果 */
.render-params-overlay {
  position: absolute;
  top: 12px;
  left: 12px;
  width: 260px;
  max-height: calc(100% - 24px);
  overflow-y: auto;
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-w85, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.2));
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
  z-index: 10;
}

/* 深色主题下浮动面板样式 */
[data-theme="dark"] .render-params-overlay {
  background: var(--cpq-overlay-b75, rgba(0, 0, 0, 0.75));
  border-color: var(--cpq-glass-border, rgba(255, 255, 255, 0.1));
}

/* Collapse 样式调整 - 更紧凑 */
.render-params-overlay :deep(.ant-collapse) {
  background: transparent;
  border: none;
}

.render-params-overlay :deep(.ant-collapse-item) {
  border-bottom: 1px solid var(--cpq-glass-border, rgba(255, 255, 255, 0.1));
}

.render-params-overlay :deep(.ant-collapse-item:last-child) {
  border-bottom: none;
}

.render-params-overlay :deep(.ant-collapse-header) {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary, #E8ECEF);
}

.render-params-overlay :deep(.ant-collapse-content) {
  background: transparent;
}

.render-params-overlay :deep(.ant-collapse-content-box) {
  padding: 4px 12px 12px;
}

.preview-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  color: var(--cpq-text-muted, #6E7582);
  font-size: var(--cpq-font-size-base);
}
</style>