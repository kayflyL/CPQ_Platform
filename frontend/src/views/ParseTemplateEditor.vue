<template>
  <div class="parse-template-editor">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>解析模板配置</h2>
      <a-space v-if="store.currentTemplate">
        <a-button @click="handleCancel">
          取消
        </a-button>
        <a-button
          type="primary"
          :loading="saving"
          @click="handleSaveTemplate"
        >
          <template #icon><SaveOutlined /></template>
          保存
        </a-button>
        <a-button
          danger
          @click="handleDeleteTemplate"
        >
          删除
        </a-button>
      </a-space>
      <a-button
        v-else
        type="primary"
        @click="handleCreate"
      >
        <template #icon><PlusOutlined /></template>
        新建解析模板
      </a-button>
    </div>

    <!-- 列表视图：模板卡片网格 -->
    <div v-if="!store.currentTemplate" class="template-grid">
      <div v-if="store.templates.length === 0" class="grid-empty">
        <a-empty description="暂无解析模板，点击右上角新建" />
      </div>
      <div
        v-for="t in store.templates"
        :key="t.id"
        class="template-card"
        @click="handleEditCard(t.id)"
      >
        <div class="card-header">
          <div class="card-title">
            <FileExcelOutlined />
            <span>{{ t.name || '未命名模板' }}</span>
          </div>
          <div class="card-actions" @click.stop>
            <a-button size="small" @click="handleEditCard(t.id)">
              <template #icon><EditOutlined /></template>
            </a-button>
            <a-button size="small" danger @click="handleDeleteCard(t.id)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
        </div>
        <div class="card-info">
          <div v-if="t.description" class="info-row">
            <span class="info-label">描述：</span>
            <span class="info-value">{{ t.description }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">静态字段：</span>
            <span class="info-value">{{ t.staticBindings.length }} 个</span>
          </div>
          <div class="info-row">
            <span class="info-label">动态区域：</span>
            <span class="info-value">{{ t.dynamicRegions.length }} 个</span>
          </div>
        </div>
        <div class="card-footer">
          <span class="update-time">创建于 {{ formatDate(t.createdAt) }}</span>
        </div>
      </div>
    </div>

    <!-- 新建模板弹窗 -->
    <a-modal
      v-model:open="createModalVisible"
      title="新建解析模板"
      @ok="handleCreateConfirm"
      :confirm-loading="createLoading"
    >
      <a-form layout="vertical">
        <a-form-item label="模板名称" required>
          <a-input
            v-model:value="newTemplateName"
            placeholder="请输入模板名称"
            @press-enter="handleCreateConfirm"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 编辑视图：模板基本信息 -->
    <div v-if="store.currentTemplate" class="template-meta">
      <a-form layout="inline" size="small">
        <a-form-item label="模板名称">
          <a-input
            v-model:value="store.currentTemplate.name"
            placeholder="输入模板名称"
            style="width: 200px;"
          />
        </a-form-item>
        <a-form-item label="描述">
          <a-input
            v-model:value="store.currentTemplate.description"
            placeholder="可选描述"
            style="width: 300px;"
          />
        </a-form-item>
      </a-form>
    </div>

    <!-- 主内容区 -->
    <div v-if="store.currentTemplate" class="main-content">
      <!-- 隐藏的文件输入 -->
      <input
        ref="fileInputRef"
        type="file"
        accept=".xlsx,.xls"
        style="display: none;"
        @change="(e: Event) => { const input = e.target as HTMLInputElement; if (input.files?.[0]) handleSampleUpload(input.files[0]); }"
      />

      <!-- 上排：左中右三栏 -->
      <div class="top-row">
        <!-- 左栏：静态字段配置 -->
        <div class="side-panel left-panel">
          <div class="panel-title">静态字段绑定</div>
          <div class="static-config">
            <!-- 上传样本 -->
            <div class="upload-bar">
              <a-button
                size="small"
                :loading="templateStore.editorState.loading"
                @click="triggerSampleUpload"
              >
                <template #icon><UploadOutlined /></template>
                {{ sampleLoaded ? '重新上传' : '上传样本' }}
              </a-button>
              <a-tag v-if="sampleLoaded" color="green" size="small">已加载</a-tag>
            </div>

            <!-- 单元格绑定表单 -->
            <div v-if="!selectedCell" class="empty-hint">
              点击预览区单元格进行绑定
            </div>
            <div v-else class="binding-form">
              <a-descriptions :column="1" size="small" bordered>
                <a-descriptions-item label="工作表">{{ currentSheetName }}</a-descriptions-item>
                <a-descriptions-item label="单元格">{{ selectedCellAddress }}</a-descriptions-item>
                <a-descriptions-item label="当前值">{{ selectedCell.value ?? '(空)' }}</a-descriptions-item>
              </a-descriptions>
              <a-form layout="inline" size="small" style="margin-top: 8px;">
                <a-form-item label="绑定字段">
                  <a-select
                    v-model:value="bindingFieldKey"
                    placeholder="选择业务字段"
                    allow-clear
                    show-search
                    :filter-option="filterOption"
                    style="width: 160px;"
                  >
                    <a-select-opt-group label="表头字段">
                      <a-select-option v-for="f in headerFields" :key="f.key" :value="f.key">{{ f.label }}</a-select-option>
                    </a-select-opt-group>
                    <a-select-opt-group label="产品字段">
                      <a-select-option v-for="f in productFields" :key="f.key" :value="f.key">{{ f.label }}</a-select-option>
                    </a-select-opt-group>
                    <a-select-opt-group label="配置字段">
                      <a-select-option v-for="f in configFields" :key="f.key" :value="f.key">{{ f.label }}</a-select-option>
                    </a-select-opt-group>
                  </a-select>
                </a-form-item>
                <a-form-item>
                  <a-space>
                    <a-button type="primary" size="small" @click="saveStaticBinding">保存</a-button>
                    <a-button size="small" @click="removeStaticBinding">移除</a-button>
                  </a-space>
                </a-form-item>
              </a-form>
            </div>

            <!-- 已绑定列表 -->
            <div class="binding-list" v-if="store.currentTemplate.staticBindings.length > 0">
              <div class="panel-subtitle">已绑定 ({{ store.currentTemplate.staticBindings.length }})</div>
              <div
                v-for="b in store.currentTemplate.staticBindings"
                :key="b.id"
                :class="['binding-item', { 'binding-highlight': b.id === highlightedBindingId }]"
                :ref="(el) => setBindingRef(b.id, el as HTMLElement)"
                @click="onBindingItemClick(b)"
              >
                <span class="binding-cell">{{ b.cellAddress }}</span>
                <span class="binding-field">{{ b.fieldKey }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 中栏：预览 + 热力图 -->
        <div class="center-panel">
          <div class="panel-title">
            实时预览
            <a-switch
              v-model:checked="heatmapEnabled"
              checked-children="热力图"
              un-checked-children="纯预览"
              size="small"
            />
            <a-button-group size="small" style="margin-left: auto;">
              <a-button @click="zoomOut" :disabled="previewScale <= MIN_SCALE">
                <ZoomOutOutlined />
              </a-button>
              <a-button @click="resetZoom" style="min-width: 50px;">
                {{ Math.round(previewScale * 100) }}%
              </a-button>
              <a-button @click="zoomIn" :disabled="previewScale >= MAX_SCALE">
                <ZoomInOutlined />
              </a-button>
            </a-button-group>
            <a-button
              size="small"
              :loading="previewing"
              :disabled="!sampleLoaded || !store.currentTemplate"
              @click="handlePreview"
            >
              <template #icon><EyeOutlined /></template>
              刷新预览
            </a-button>
          </div>

          <div v-if="!sampleLoaded" class="preview-empty">
            上传 Excel 样本后显示预览
          </div>
          <div v-else class="preview-area">
            <!-- Excel 表格 + 热力图覆盖 -->
            <div class="excel-preview-wrap">
              <div class="excel-preview-scaler" :style="{ transform: `scale(${previewScale})`, transformOrigin: 'top left' }">
                <ExcelTable
                  :sheets="templateStore.templateData!.sheets"
                  :overlayMap="heatmapEnabled ? heatmapOverlayMap : emptyOverlayMap"
                  :a4Preview="false"
                  @cell-click="onPreviewCellClick"
                />
              </div>
              <div v-if="heatmapEnabled" class="heatmap-legend">
                <div class="legend-item">
                  <span class="legend-color" style="background: var(--cpq-overlay-info20);"></span>
                  静态字段
                </div>
                <div class="legend-item">
                  <span class="legend-color" style="background: var(--cpq-overlay-success15);"></span>
                  动态区域
                </div>
              </div>
            </div>

            <!-- 解析结果预览 -->
            <div v-if="previewResult" class="preview-result">
              <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
                <a-button size="small" @click="clearPreview">
                  清除预览
                </a-button>
              </div>
              <a-alert
                v-if="previewResult.warnings.length > 0"
                type="warning"
                show-icon
                size="small"
                style="margin-bottom: 8px;"
              >
                <template #message>
                  <div v-for="(w, i) in previewResult.warnings" :key="i">{{ w }}</div>
                </template>
              </a-alert>
              <div class="preview-section" v-if="Object.keys(previewResult.staticData).length > 0">
                <div class="preview-section-title">静态字段</div>
                <a-descriptions :column="2" size="small" bordered>
                  <a-descriptions-item
                    v-for="(val, key) in previewResult.staticData"
                    :key="key"
                    :label="String(key)"
                  >{{ val ?? '—' }}</a-descriptions-item>
                </a-descriptions>
              </div>
              <div
                v-for="(rows, regionName) in previewResult.dynamicData"
                :key="regionName"
                class="preview-section"
              >
                <div class="preview-section-title">
                  {{ regionName }}
                  <a-tag color="blue" size="small">{{ rows.length }} 行</a-tag>
                </div>
                <a-table
                  :dataSource="rows.map((r, i) => ({ ...r, _key: i }))"
                  :columns="getDynamicColumns(rows)"
                  :pagination="false"
                  size="small"
                  rowKey="_key"
                  :scroll="{ y: 150 }"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- 右栏：动态区域配置 -->
        <div class="side-panel right-panel">
          <div class="panel-title">动态区域</div>
          <div class="dynamic-config">
            <div class="toolbar">
              <a-button type="primary" size="small" @click="addDynamicRegion">
                <template #icon><PlusOutlined /></template>
                添加区域
              </a-button>
            </div>
            <div v-if="store.currentTemplate.dynamicRegions.length === 0" class="tab-empty">
              暂无动态区域
            </div>
            <a-collapse v-else v-model:activeKey="expandedRegions" ghost>
              <a-collapse-panel
                v-for="region in store.currentTemplate.dynamicRegions"
                :key="region.id"
                :header="region.name || '未命名区域'"
              >
                <template #extra>
                  <a-button type="link" danger size="small" @click.stop="removeDynamicRegion(region.id)">删除</a-button>
                </template>
                <a-form layout="vertical" size="small">
                  <a-row :gutter="8">
                    <a-col :span="12">
                      <a-form-item label="名称">
                        <a-input v-model:value="region.name" placeholder="如：L6配件" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="类型">
                        <a-select v-model:value="region.regionType">
                          <a-select-option value="l6">L6</a-select-option>
                          <a-select-option value="kp">KP</a-select-option>
                          <a-select-option value="custom">自定义</a-select-option>
                        </a-select>
                      </a-form-item>
                    </a-col>
                  </a-row>
                  <a-row :gutter="8">
                    <a-col :span="12">
                      <a-form-item label="字段 Key" tooltip="供导出模板引用的唯一标识，如 l6_details">
                        <a-input v-model:value="region.fieldKey" placeholder="如：l6_details" />
                      </a-form-item>
                    </a-col>
                    <a-col :span="12">
                      <a-form-item label="字段标签" tooltip="导出模板中显示的名称，如 L6配件明细">
                        <a-input v-model:value="region.fieldLabel" placeholder="如：L6配件明细" />
                      </a-form-item>
                    </a-col>
                  </a-row>
                  <a-form-item label="起始关键词">
                    <a-input v-model:value="region.startKeywords" placeholder="如：L6（逗号分隔）" />
                  </a-form-item>
                  <a-form-item label="结束关键词">
                    <a-input v-model:value="region.endKeywords" placeholder="如：Keyparts,KP" />
                  </a-form-item>
                  <a-form-item label="字段列映射">
                    <div class="field-mapping-list">
                      <div v-for="(col, field) in region.fieldMapping" :key="field" class="field-mapping-row">
                        <span class="fm-field">{{ field }}</span>
                        <a-select :value="col" @change="(val: string) => region.fieldMapping[field] = val" size="small" style="width: 70px;">
                          <a-select-option v-for="l in columnLetters" :key="l" :value="l">{{ l }}</a-select-option>
                        </a-select>
                        <a-button type="link" danger size="small" @click="removeFieldMapping(region, field)">×</a-button>
                      </div>
                      <div class="add-field-row">
                        <a-input v-model:value="newFieldName" placeholder="字段名" size="small" style="width: 80px;" />
                        <a-select v-model:value="newFieldCol" placeholder="列" size="small" style="width: 70px;">
                          <a-select-option v-for="l in columnLetters" :key="l" :value="l">{{ l }}</a-select-option>
                        </a-select>
                        <a-button size="small" @click="addFieldMapping(region)">+</a-button>
                      </div>
                    </div>
                  </a-form-item>
                </a-form>
              </a-collapse-panel>
            </a-collapse>
          </div>
        </div>
      </div>

      <!-- 下排：绑定总览 + KP分类 + Excel解析 -->
      <div class="bottom-panel">
        <a-tabs v-model:activeKey="bottomTab" type="card" size="small">
          <!-- Tab1: 绑定总览 -->
          <a-tab-pane key="bindingOverview" tab="绑定总览">
            <div class="binding-overview">
              <div class="overview-columns">
                <!-- 静态字段总览 -->
                <div class="overview-section">
                  <div class="overview-title">
                    <span class="legend-color" style="background: var(--cpq-overlay-info20);"></span>
                    静态字段 ({{ store.currentTemplate.staticBindings.length }})
                  </div>
                  <div v-if="store.currentTemplate.staticBindings.length === 0" class="overview-empty">暂无绑定</div>
                  <div v-else class="overview-table-wrap">
                    <table class="overview-table">
                      <thead><tr><th>单元格</th><th>字段</th><th>工作表</th></tr></thead>
                      <tbody>
                        <tr
                          v-for="b in store.currentTemplate.staticBindings"
                          :key="b.id"
                          @click="onOverviewStaticClick(b)"
                          class="overview-row"
                        >
                          <td class="mono">{{ b.cellAddress }}</td>
                          <td>{{ b.fieldKey }}</td>
                          <td>{{ b.sheetName }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                <!-- 动态区域总览 -->
                <div class="overview-section">
                  <div class="overview-title">
                    <span class="legend-color" style="background: var(--cpq-overlay-success15);"></span>
                    动态区域 ({{ store.currentTemplate.dynamicRegions.length }})
                  </div>
                  <div v-if="store.currentTemplate.dynamicRegions.length === 0" class="overview-empty">暂无区域</div>
                  <div v-else class="overview-table-wrap">
                    <table class="overview-table">
                      <thead><tr><th>名称</th><th>类型</th><th>起始</th><th>结束</th><th>列映射</th></tr></thead>
                      <tbody>
                        <tr
                          v-for="r in store.currentTemplate.dynamicRegions"
                          :key="r.id"
                          @click="onOverviewDynamicClick(r)"
                          class="overview-row"
                        >
                          <td>{{ r.name || '未命名' }}</td>
                          <td><a-tag size="small">{{ r.regionType }}</a-tag></td>
                          <td class="mono">{{ r.startKeywords || '—' }}</td>
                          <td class="mono">{{ r.endKeywords || '—' }}</td>
                          <td class="mono">{{ Object.entries(r.fieldMapping).map(([f,c]) => `${f}:${c}`).join(', ') || '—' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </a-tab-pane>

          <!-- Tab2: KP分类映射 -->
          <a-tab-pane key="kpCategory" tab="KP分类映射">
            <div class="kp-category-config">
              <div class="toolbar">
                <a-button type="primary" size="small" @click="addKpMapping">
                  <template #icon><PlusOutlined /></template>
                  添加映射
                </a-button>
              </div>

              <a-table
                :dataSource="store.currentTemplate.kpCategoryMappings"
                :columns="kpMappingColumns"
                :pagination="false"
                size="small"
                rowKey="id"
                :scroll="{ y: 300 }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'keyword'">
                    <a-input v-model:value="record.keyword" size="small" placeholder="关键词" />
                  </template>
                  <template v-if="column.key === 'category'">
                    <a-select
                      v-model:value="record.category"
                      size="small"
                      style="width: 100%;"
                      placeholder="选择分类"
                      allow-clear
                    >
                      <a-select-option value="CPU">CPU</a-select-option>
                      <a-select-option value="Memory">Memory</a-select-option>
                      <a-select-option value="Storage">Storage</a-select-option>
                      <a-select-option value="Network">Network</a-select-option>
                      <a-select-option value="PSU">PSU</a-select-option>
                      <a-select-option value="Chassis">Chassis</a-select-option>
                      <a-select-option value="Motherboard">Motherboard</a-select-option>
                      <a-select-option value="Other">Other</a-select-option>
                    </a-select>
                  </template>
                  <template v-if="column.key === 'action'">
                    <a-popconfirm
                      title="确定删除？"
                      ok-text="确定"
                      cancel-text="取消"
                      @confirm="removeKpMapping(record)"
                    >
                      <a-button type="link" danger size="small">删除</a-button>
                    </a-popconfirm>
                  </template>
                </template>
                <template #emptyText>
                  <a-empty description="暂无分类映射" />
                </template>
              </a-table>
            </div>
          </a-tab-pane>

          <!-- Tab4: Excel解析 -->
          <a-tab-pane key="parse" tab="Excel解析">
            <div class="excel-parse-config">
              <!-- 选择模板 -->
              <div class="parse-section">
                <div class="section-title">1. 选择解析模板</div>
                <a-select
                  v-model:value="parseTemplateId"
                  placeholder="选择已保存的解析模板"
                  style="width: 100%; max-width: 400px;"
                  show-search
                  :filter-option="filterOption"
                >
                  <a-select-option v-for="t in store.templateList" :key="t.id" :value="t.id">
                    {{ t.name }}
                    <span v-if="t.description" style="color: var(--cpq-text-muted); font-size: 12px; margin-left: 8px;">
                      {{ t.description }}
                    </span>
                  </a-select-option>
                </a-select>
              </div>

              <!-- 上传文件 -->
              <div class="parse-section">
                <div class="section-title">2. 上传 Excel 文件</div>
                <a-upload-dragger
                  :before-upload="handleParseUpload"
                  :show-upload-list="false"
                  accept=".xlsx,.xls"
                  :disabled="!parseTemplateId"
                >
                  <p class="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p class="ant-upload-text">点击或拖拽 Excel 文件到此区域</p>
                  <p class="ant-upload-hint">
                    将使用模板「{{ parseTemplateName }}」进行解析
                  </p>
                </a-upload-dragger>
              </div>

              <!-- 解析结果 -->
              <div v-if="parseResult" class="parse-section">
                <div class="section-title">
                  3. 解析结果
                  <a-button
                    v-if="parseResult"
                    size="small"
                    @click="handleExportJson"
                    style="margin-left: auto;"
                  >
                    <template #icon><DownloadOutlined /></template>
                    导出 JSON
                  </a-button>
                </div>

                <!-- 警告信息 -->
                <a-alert
                  v-if="parseResult.warnings.length > 0"
                  type="warning"
                  show-icon
                  style="margin-bottom: 12px;"
                >
                  <template #message>
                    <div v-for="(w, i) in parseResult.warnings" :key="i">{{ w }}</div>
                  </template>
                </a-alert>

                <!-- 静态字段结果 -->
                <div v-if="Object.keys(parseResult.staticData).length > 0" class="result-block">
                  <div class="result-title">基础信息</div>
                  <a-descriptions :column="2" size="small" bordered>
                    <a-descriptions-item
                      v-for="(val, key) in parseResult.staticData"
                      :key="key"
                      :label="String(key)"
                    >
                      {{ val ?? '—' }}
                    </a-descriptions-item>
                  </a-descriptions>
                </div>

                <!-- 动态区域结果 -->
                <div
                  v-for="(rows, regionName) in parseResult.dynamicData"
                  :key="regionName"
                  class="result-block"
                >
                  <div class="result-title">
                    {{ regionName }}
                    <a-tag color="blue">{{ rows.length }} 行</a-tag>
                  </div>
                  <a-table
                    :dataSource="rows.map((r, i) => ({ ...r, _key: i }))"
                    :columns="getParseColumns(rows)"
                    :pagination="rows.length > 10 ? { pageSize: 10 } : false"
                    size="small"
                    rowKey="_key"
                    :scroll="{ x: 'max-content' }"
                  />
                </div>

                <a-button @click="parseResult = null" style="margin-top: 12px;">
                  重新解析
                </a-button>
              </div>
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined,
  SaveOutlined,
  UploadOutlined,
  EyeOutlined,
  InboxOutlined,
  DownloadOutlined,
  EditOutlined,
  DeleteOutlined,
  FileExcelOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  CheckCircleOutlined
} from '@ant-design/icons-vue'
import { useParseTemplateStore } from '@/store/parseTemplate'
import { useTemplateStore } from '@/store/template'
import type { DynamicRegion, ParsedResult, ParsedRow } from '@/types/parseTemplate'
import type { RenderCell } from '@/types/template'
import { parseExcelByTemplate } from '@/utils/excel-parser'
import ExcelTable from '@/components/ExcelTable.vue'

const store = useParseTemplateStore()
const templateStore = useTemplateStore()

// UI状态
const bottomTab = ref('bindingOverview')
const heatmapEnabled = ref(true)
const selectedTemplateId = ref<string | undefined>(undefined)
const saving = ref(false)
const previewing = ref(false)
const sampleLoaded = ref(false)
const previewResult = ref<ParsedResult | null>(null)
const isNewTemplate = ref(false)

// 预览缩放控制
const previewScale = ref(1)
const MIN_SCALE = 0.5
const MAX_SCALE = 2
const SCALE_STEP = 0.1

function zoomIn() {
  if (previewScale.value < MAX_SCALE) {
    previewScale.value = Math.min(MAX_SCALE, +(previewScale.value + SCALE_STEP).toFixed(1))
  }
}

function zoomOut() {
  if (previewScale.value > MIN_SCALE) {
    previewScale.value = Math.max(MIN_SCALE, +(previewScale.value - SCALE_STEP).toFixed(1))
  }
}

function resetZoom() {
  previewScale.value = 1
}

// 新建模板弹窗
const createModalVisible = ref(false)
const newTemplateName = ref('')
const createLoading = ref(false)

// 静态字段绑定
const selectedCell = ref<RenderCell | null>(null)
const bindingFieldKey = ref('')

// 热力图联动
const configPanelRef = ref<HTMLElement | null>(null)
const highlightedBindingId = ref<string | null>(null)
const bindingRefs = new Map<string, HTMLElement>()
const fileInputRef = ref<HTMLInputElement | null>(null)

function setBindingRef(id: string, el: HTMLElement | null) {
  if (el) {
    bindingRefs.set(id, el)
  } else {
    bindingRefs.delete(id)
  }
}

function scrollToBinding(id: string) {
  const el = bindingRefs.get(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

// 热力图覆盖色映射
const heatmapOverlayMap = computed(() => {
  const map = new Map<string, string>()
  const tpl = store.currentTemplate
  if (!tpl) return map

  // 静态字段：蓝色
  for (const b of tpl.staticBindings) {
    map.set(`${b.sheetName}!${b.cellAddress}`, 'var(--cpq-overlay-info20)')
  }

  // 动态区域：绿色（标记起始关键词所在单元格及下方区域）
  for (const region of tpl.dynamicRegions) {
    if (region.startKeywords && templateStore.templateData) {
      for (const sheet of templateStore.templateData.sheets) {
        for (const row of sheet.cells) {
          for (const cell of row) {
            const cellVal = String(cell.value ?? '').trim()
            if (region.startKeywords.split(/[,，]/).some(kw => cellVal.includes(kw.trim()))) {
              const key = `${sheet.name}!${colToLetter(cell.col)}${cell.row}`
              map.set(key, 'var(--cpq-overlay-success15)')
              for (let r = cell.row + 1; r <= Math.min(cell.row + 20, sheet.rowCount); r++) {
                const dynKey = `${sheet.name}!${colToLetter(cell.col)}${r}`
                if (!map.has(dynKey)) {
                  map.set(dynKey, 'var(--cpq-overlay-success15)')
                }
              }
            }
          }
        }
      }
    }
  }

  return map
})

// 空覆盖图（热力图关闭时使用）
const emptyOverlayMap = computed(() => new Map<string, string>())

// 预览区单元格点击 → 填充左栏绑定表单
function onPreviewCellClick(cell: RenderCell) {
  const addr = `${colToLetter(cell.col)}${cell.row}`
  const sheetName = currentSheetName.value
  const tpl = store.currentTemplate
  if (!tpl) return

  selectedCell.value = cell
  const existing = tpl.staticBindings.find(
    b => b.sheetName === sheetName && b.cellAddress === addr
  )
  bindingFieldKey.value = existing?.fieldKey || ''
}

// 左栏已绑定项点击 → 预览区高亮
function onBindingItemClick(b: { id: string; sheetName: string; cellAddress: string; fieldKey: string }) {
  highlightedBindingId.value = b.id
  // 找到对应单元格并选中
  if (templateStore.templateData) {
    for (const sheet of templateStore.templateData.sheets) {
      if (sheet.name === b.sheetName) {
        for (const row of sheet.cells) {
          for (const cell of row) {
            const addr = `${colToLetter(cell.col)}${cell.row}`
            if (addr === b.cellAddress) {
              selectedCell.value = cell
              bindingFieldKey.value = b.fieldKey
              break
            }
          }
        }
      }
    }
  }
  setTimeout(() => { highlightedBindingId.value = null }, 2000)
}

// 绑定总览：静态字段点击
function onOverviewStaticClick(b: { id: string; sheetName: string; cellAddress: string; fieldKey: string }) {
  onBindingItemClick(b)
}

// 绑定总览：动态区域点击 → 展开对应 Collapse
function onOverviewDynamicClick(region: DynamicRegion) {
  if (!expandedRegions.value.includes(region.id)) {
    expandedRegions.value.push(region.id)
  }
}

// 触发文件上传
function triggerSampleUpload() {
  fileInputRef.value?.click()
}

// 动态区域
const expandedRegions = ref<string[]>([])
const newFieldName = ref('')
const newFieldCol = ref('')

// Excel解析Tab状态
const parseTemplateId = ref<string | undefined>(undefined)
const parseResult = ref<ParsedResult | null>(null)

// 列字母
const columnLetters = 'A B C D E F G H I J K L M N O P Q R S T U V W X Y Z'.split(' ')

// 业务字段（复用template store）
const headerFields = computed(() => templateStore.businessFields.filter(f => f.category === 'opportunity'))
const productFields = computed(() => templateStore.businessFields.filter(f => f.category === 'item'))
const configFields = computed(() => templateStore.businessFields.filter(f => f.category === 'l6' || f.category === 'kp'))

// 当前选中单元格信息
const currentSheetName = computed(() => templateStore.currentSheet?.name || '')
const selectedCellAddress = computed(() => {
  if (!selectedCell.value) return ''
  return `${colToLetter(selectedCell.value.col)}${selectedCell.value.row}`
})

// KP分类映射表格列
const kpMappingColumns = [
  { title: '关键词', dataIndex: 'keyword', key: 'keyword', width: 200 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 150 },
  { title: '操作', key: 'action', width: 80 }
]

// 初始化
// store 在创建时已自动加载数据，无需 onMounted

// 格式化日期
function formatDate(timestamp: number): string {
  const date = new Date(timestamp)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 新建模板（打开弹窗）
function handleCreate() {
  newTemplateName.value = ''
  createModalVisible.value = true
}

// 确认新建模板
function handleCreateConfirm() {
  if (!newTemplateName.value.trim()) {
    message.warning('请输入模板名称')
    return
  }
  createLoading.value = true
  try {
    const newTpl = store.createNewTemplate()
    newTpl.name = newTemplateName.value.trim()
    createModalVisible.value = false
    selectedTemplateId.value = newTpl.id
    isNewTemplate.value = true
    previewResult.value = null
    sampleLoaded.value = false
    templateStore.reset()
    message.success('已创建新模板，请配置')
  } finally {
    createLoading.value = false
  }
}

// 从卡片进入编辑
function handleEditCard(id: string) {
  store.loadTemplate(id)
  selectedTemplateId.value = id
  previewResult.value = null
  sampleLoaded.value = false
  isNewTemplate.value = false
}

// 从卡片删除
function handleDeleteCard(id: string) {
  const tpl = store.templates.find(t => t.id === id)
  if (!tpl) return
  Modal.confirm({
    title: '确认删除',
    content: `确定删除模板"${tpl.name}"？`,
    okText: '确定',
    cancelText: '取消',
    okType: 'danger',
    onOk() {
      store.deleteTemplate(id)
      store.saveToStorage()
      message.success('已删除')
    }
  })
}

// 选择模板
function onTemplateSelect(id: string | undefined) {
  if (id) {
    store.loadTemplate(id)
    message.success(`已加载模板`)
  } else {
    store.currentTemplate = null
  }
  previewResult.value = null
  sampleLoaded.value = false
  isNewTemplate.value = false
}

// 新建模板
function handleNewTemplate() {
  store.createNewTemplate()
  selectedTemplateId.value = undefined
  previewResult.value = null
  sampleLoaded.value = false
  isNewTemplate.value = true
  templateStore.reset()
  message.info('已创建新模板，请配置')
}

// 取消新建或编辑
function handleCancel() {
  if (isNewTemplate.value) {
    // 取消新建：重置模板
    templateStore.reset()
  }
  // 无论新建还是编辑，都返回列表
  store.currentTemplate = null
  selectedTemplateId.value = undefined
  previewResult.value = null
  sampleLoaded.value = false
  isNewTemplate.value = false
}

// 保存模板
function handleSaveTemplate() {
  const tpl = store.currentTemplate
  if (!tpl) return
  if (!tpl.name.trim()) {
    message.warning('请输入模板名称')
    return
  }
  saving.value = true
  try {
    store.saveTemplate(tpl)
    store.saveToStorage()
    selectedTemplateId.value = tpl.id
    isNewTemplate.value = false
    message.success('模板已保存')
  } finally {
    saving.value = false
  }
}

// 删除模板
function handleDeleteTemplate() {
  const tpl = store.currentTemplate
  if (!tpl) return
  Modal.confirm({
    title: '确认删除',
    content: `确定删除模板"${tpl.name}"？`,
    okText: '确定',
    cancelText: '取消',
    onOk() {
      store.deleteTemplate(tpl.id)
      store.saveToStorage()
      selectedTemplateId.value = undefined
      store.currentTemplate = null
      previewResult.value = null
      sampleLoaded.value = false
      isNewTemplate.value = false
      templateStore.reset()
      message.success('已删除')
    }
  })
}

// 上传Excel样本
async function handleSampleUpload(file: File) {
  if (!file.name.match(/\.xlsx?$/i)) {
    message.error('仅支持 .xlsx 格式')
    return false
  }
  try {
    await templateStore.loadTemplate(file)
    sampleLoaded.value = true
    selectedCell.value = null
    previewResult.value = null
    message.success(`样本加载成功：${file.name}`)
  } catch (err) {
    console.error(err)
    message.error('Excel 解析失败')
  }
  return false
}

// 点击单元格
function onCellClick(cell: RenderCell) {
  selectedCell.value = cell
  const addr = selectedCellAddress.value
  const tpl = store.currentTemplate
  if (!tpl) return
  const existing = tpl.staticBindings.find(
    b => b.sheetName === currentSheetName.value && b.cellAddress === addr
  )
  bindingFieldKey.value = existing?.fieldKey || ''
}

// 保存静态绑定
function saveStaticBinding() {
  if (!selectedCell.value || !bindingFieldKey.value) {
    message.warning('请选择要绑定的字段')
    return
  }
  const tpl = store.currentTemplate
  if (!tpl) return

  const binding = {
    id: `${currentSheetName.value}_${selectedCellAddress.value}`,
    sheetName: currentSheetName.value,
    cellAddress: selectedCellAddress.value,
    fieldKey: bindingFieldKey.value,
    dataType: 'static' as const,
    templateRow: undefined
  }

  const idx = tpl.staticBindings.findIndex(
    b => b.sheetName === binding.sheetName && b.cellAddress === binding.cellAddress
  )
  if (idx >= 0) {
    tpl.staticBindings[idx] = binding
  } else {
    tpl.staticBindings.push(binding)
  }
  message.success('绑定已保存')
}

// 移除静态绑定
function removeStaticBinding() {
  if (!selectedCell.value) return
  const tpl = store.currentTemplate
  if (!tpl) return
  tpl.staticBindings = tpl.staticBindings.filter(
    b => !(b.sheetName === currentSheetName.value && b.cellAddress === selectedCellAddress.value)
  )
  bindingFieldKey.value = ''
  message.success('绑定已移除')
}

// 搜索过滤
function filterOption(input: string, option: Record<string, unknown>) {
  const label = option.label as string | undefined
  return label?.toLowerCase().includes(input.toLowerCase())
}

// 动态区域操作
function addDynamicRegion() {
  const tpl = store.currentTemplate
  if (!tpl) return
  const region: DynamicRegion = {
    id: `region_${Date.now()}`,
    name: '',
    regionType: 'custom',
    fieldKey: `region_${Date.now()}`,
    fieldLabel: '',
    startKeywords: '',
    endKeywords: '',
    fieldMapping: {}
  }
  tpl.dynamicRegions.push(region)
  expandedRegions.value.push(region.id)
}

function removeDynamicRegion(id: string) {
  const tpl = store.currentTemplate
  if (!tpl) return
  tpl.dynamicRegions = tpl.dynamicRegions.filter(r => r.id !== id)
}

function addFieldMapping(region: DynamicRegion) {
  if (!newFieldName.value || !newFieldCol.value) {
    message.warning('请输入字段名和列')
    return
  }
  region.fieldMapping[newFieldName.value] = newFieldCol.value
  newFieldName.value = ''
  newFieldCol.value = ''
}

function removeFieldMapping(region: DynamicRegion, field: string) {
  delete region.fieldMapping[field]
}

// KP分类映射
function addKpMapping() {
  const tpl = store.currentTemplate
  if (!tpl) return
  tpl.kpCategoryMappings.push({
    id: `kp_${Date.now()}`,
    keyword: '',
    category: ''
  })
}

function removeKpMapping(record: { id: string }) {
  const tpl = store.currentTemplate
  if (!tpl) return
  tpl.kpCategoryMappings = tpl.kpCategoryMappings.filter(m => m.id !== record.id)
}

// 实时预览
// 清除解析预览，恢复实时预览表
function clearPreview() {
  previewResult.value = null
  nextTick(() => {
    if (templateStore.templateData) {
      templateStore.templateData = { ...templateStore.templateData }
    }
  })
}

async function handlePreview() {
  const tpl = store.currentTemplate
  if (!tpl || !templateStore.templateData) return

  previewing.value = true
  try {
    const result = await parseExcelByTemplate(
      templateStore.templateData.fileBuffer,
      tpl
    )
    previewResult.value = result
  } catch (err) {
    console.error(err)
    message.error('预览解析失败')
  } finally {
    previewing.value = false
  }
}

// 动态区域表格列生成
function getDynamicColumns(rows: ParsedRow[]) {
  if (rows.length === 0) return []
  const keys = Object.keys(rows[0]).filter(k => k !== '_key')
  return keys.map(k => ({
    title: k,
    dataIndex: k,
    key: k,
    ellipsis: true
  }))
}

// 工具函数
function colToLetter(col: number): string {
  let result = ''
  while (col > 0) {
    const mod = (col - 1) % 26
    result = String.fromCharCode(65 + mod) + result
    col = Math.floor((col - 1) / 26)
  }
  return result
}

// Excel解析Tab相关函数
const parseTemplateName = computed(() => {
  if (!parseTemplateId.value) return ''
  const tpl = store.templateList.find(t => t.id === parseTemplateId.value)
  return tpl?.name || ''
})

async function handleParseUpload(file: File) {
  if (!parseTemplateId.value) {
    message.warning('请先选择模板')
    return false
  }
  
  const template = store.templates.find(t => t.id === parseTemplateId.value)
  if (!template) {
    message.error('模板不存在')
    return false
  }

  try {
    const buffer = await file.arrayBuffer()
    const result = await parseExcelByTemplate(buffer, template)
    parseResult.value = result
    message.success('解析完成')
  } catch (err) {
    console.error(err)
    message.error('解析失败')
  }
  return false
}

function handleExportJson() {
  if (!parseResult.value) return
  
  const data = {
    staticData: parseResult.value.staticData,
    dynamicData: parseResult.value.dynamicData,
    exportedAt: new Date().toISOString()
  }
  
  const json = JSON.stringify(data, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `parsed_${parseTemplateName.value}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  message.success('导出成功')
}

function getParseColumns(rows: ParsedRow[]) {
  if (rows.length === 0) return []
  const keys = Object.keys(rows[0]).filter(k => k !== '_key')
  return keys.map(k => ({
    title: k,
    dataIndex: k,
    key: k,
    ellipsis: true
  }))
}
</script>

<style scoped>
.parse-template-editor {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.page-header h2 {
  margin: 0;
  color: var(--cpq-text-light);
}

.template-meta {
  margin-bottom: 12px;
  flex-shrink: 0;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.top-row {
  display: grid;
  grid-template-columns: 25% 50% 25%;
  gap: 12px;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.side-panel {
  background: var(--cpq-bg-card);
  border: 1px solid var(--cpq-border-dark);
  border-radius: 6px;
  padding: 12px;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.center-panel {
  background: var(--cpq-bg-card);
  border: 1px solid var(--cpq-border-dark);
  border-radius: 6px;
  padding: 12px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.bottom-panel {
  background: var(--cpq-bg-card);
  border: 1px solid var(--cpq-border-dark);
  border-radius: 6px;
  padding: 12px;
  overflow: auto;
  max-height: 300px;
  flex-shrink: 0;
}

.upload-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.preview-area {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #ffffff;
}

.excel-preview-wrap {
  overflow: auto;
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.excel-preview-wrap::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.excel-preview-wrap::-webkit-scrollbar-track {
  background: var(--cpq-bg-dark);
  border-radius: 5px;
}

.excel-preview-wrap::-webkit-scrollbar-thumb {
  background: var(--cpq-accent-primary);
  border-radius: 5px;
}

.excel-preview-wrap::-webkit-scrollbar-thumb:hover {
  background: var(--cpq-accent-primary-light);
}

.excel-preview-wrap::-webkit-scrollbar-corner {
  background: var(--cpq-bg-dark);
}

.excel-preview-scaler {
  display: inline-block;
  width: fit-content;
  min-width: 100%;
}

.preview-result {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.binding-overview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.overview-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.overview-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.overview-title {
  font-weight: 600;
  color: var(--cpq-text-light);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--cpq-border-dark);
}

.overview-empty {
  color: var(--cpq-text-quaternary);
  text-align: center;
  padding: 20px;
  font-size: 13px;
}

.overview-table-wrap {
  overflow: auto;
  max-height: 200px;
}

.overview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.overview-table th {
  background: var(--cpq-bg-elevated);
  color: var(--cpq-text-tertiary);
  font-weight: 500;
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid var(--cpq-border-dark);
  position: sticky;
  top: 0;
  z-index: 1;
}

.overview-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--cpq-bg-elevated);
  color: var(--cpq-text-secondary);
}

.overview-row {
  cursor: pointer;
  transition: background 0.2s;
}

.overview-row:hover {
  background: var(--cpq-bg-input);
}

.mono {
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.binding-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.heatmap-legend {
  display: flex;
  gap: 16px;
  padding: 8px 0;
  border-top: 1px solid var(--cpq-border-dark);
  margin-top: 8px;
  font-size: 12px;
  color: var(--cpq-text-tertiary);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-color {
  display: inline-block;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  border: 1px solid var(--cpq-border-dark);
}

.upload-section {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  color: var(--cpq-text-light);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--cpq-border-dark);
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-subtitle {
  font-size: 12px;
  color: var(--cpq-text-tertiary);
  margin: 12px 0 8px;
}

.static-config {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.excel-preview {
  max-height: 400px;
  overflow: auto;
}

.binding-panel {
  border-top: 1px solid var(--cpq-border-dark);
  padding-top: 12px;
}

.empty-hint {
  color: var(--cpq-text-quaternary);
  text-align: center;
  padding: 20px;
}

.tab-empty {
  color: var(--cpq-text-quaternary);
  text-align: center;
  padding: 40px 20px;
}

.binding-list {
  border-top: 1px solid var(--cpq-border-dark);
  padding-top: 8px;
  max-height: 200px;
  overflow: auto;
}

.binding-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--cpq-bg-elevated);
  margin-bottom: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.binding-item:hover {
  background: var(--cpq-bg-input);
}

.binding-highlight {
  background: var(--cpq-overlay-info20) !important;
  border: 1px solid var(--cpq-overlay-info20);
  animation: binding-flash 2s ease-out;
}

@keyframes binding-flash {
  0% { background: rgba(24, 144, 255, 0.4); }
  100% { background: var(--cpq-overlay-info20); }
}

.binding-cell {
  color: var(--cpq-color-info);
  font-family: monospace;
  font-weight: 600;
  min-width: 40px;
}

.binding-field {
  color: var(--cpq-text-light);
  flex: 1;
}

.toolbar {
  margin-bottom: 12px;
}

.field-mapping-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fm-field {
  color: var(--cpq-text-light);
  min-width: 80px;
  font-size: 13px;
}

.add-field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--cpq-border-dark);
}

.preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.preview-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preview-section {
  border: 1px solid var(--cpq-border-dark);
  border-radius: 4px;
  padding: 8px;
}

.preview-section-title {
  font-weight: 600;
  color: var(--cpq-text-light);
  margin-bottom: 8px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 模板卡片网格 */
.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.grid-empty {
  grid-column: 1 / -1;
  padding: 60px 0;
}

.template-card {
  background: var(--bg-card, var(--cpq-bg-card));
  border: 1px solid var(--border-color, var(--cpq-border-dark));
  border-radius: 8px;
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.template-card:hover {
  border-color: var(--cpq-color-info);
  box-shadow: 0 2px 8px var(--cpq-overlay-info20);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-light);
}

.card-actions {
  display: flex;
  gap: 4px;
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--cpq-text-tertiary);
}

.info-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.info-label {
  color: var(--cpq-text-quaternary);
  min-width: 70px;
}

.info-value {
  color: var(--cpq-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-footer {
  padding-top: 12px;
  border-top: 1px solid var(--cpq-border-dark);
  font-size: 12px;
  color: var(--cpq-text-quaternary);
}
</style>
