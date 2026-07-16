<template>
  <div class="workspace-page">
    <!-- 主内容区：三栏布局 -->
    <div class="content-inner">

      <!-- 配置 Tab 栏 -->
      <div class="cfg-bar">
        <div class="cfg-pills">
          <div
            v-for="name in Object.keys(store.configs)"
            :key="name"
            class="cfg-pill"
            :class="{ active: activeCfg === name }"
            @click="activeCfg = name"
            @dblclick="startRename(name as string)"
            @contextmenu="handleTabContextMenu($event, name as string)"
          >
            <template v-if="editingCfg === name">
              <input
                v-model="editingName"
                class="pill-edit-input"
                @keyup.enter="confirmRename"
                @keyup.escape="cancelRename"
                @blur="confirmRename"
                @click.stop
                ref="pillEditInput"
              />
            </template>
            <template v-else>
              <span class="pill-label">{{ name }}</span>
              <span
                class="pill-close"
                @click.stop="deleteConfigWithConfirm(name as string)"
                title="删除配置"
              >×</span>
            </template>
          </div>
        </div>
        <a-button size="small" class="cfg-add-btn" @click="addConfig">+ 添加配置</a-button>
      </div>

      <!-- 配置 Tab 右键菜单 -->
      <Teleport to="body">
        <div
          v-if="contextMenu.visible"
          class="cfg-context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
          @click="closeContextMenu"
        >
          <div class="cfg-context-item" @click="startRename(contextMenu.cfgName)">重命名</div>
          <div class="cfg-context-item cfg-context-danger" @click="deleteConfig(contextMenu.cfgName)">删除</div>
        </div>
      </Teleport>

      <!-- 三栏布局 -->
      <template v-for="(cfg, name) in store.configs" :key="name">
        <div v-if="activeCfg === name" class="three-col-layout">

          <!-- 左栏：BOM 表格 (≈22%) -->
          <div class="col-left">
            <BomTable :cfg="cfg" />
          </div>

          <!-- 中栏：服务器配置 (≈50%) -->
          <div class="col-middle">
            <!-- 配置基本信息（服务器型号 + 数量） -->
            <div class="glass card-section">
              <div class="basic-row">
                <div class="basic-field basic-field-grow">
                  <label class="basic-label">服务器型号</label>
                  <a-input
                    :value="cfg.server_model || ''"
                    @change="(e: Event) => cfg.server_model = (e.target as HTMLInputElement).value"
                    placeholder="输入服务器型号，如：PowerEdge R760"
                    size="small"
                    style="flex: 1"
                    :maxlength="100"
                  />
                </div>
                <div class="basic-field">
                  <label class="basic-label">数量</label>
                  <a-input-number
                    v-model:value="store.configQuantities[String(name)]"
                    :min="1"
                    :max="9999"
                    size="small"
                    style="width: 120px"
                    addon-after="台"
                  />
                </div>
              </div>
            </div>

            <!-- 配置描述（可折叠） -->
            <div class="glass card-desc" :class="{ expanded: descExpanded[name] }">
              <div class="desc-header" @click="descExpanded[name] = !descExpanded[name]">
                <span class="desc-title">配置描述</span>
                <span class="desc-preview" v-if="!descExpanded[name]">
                  {{ cfg.description ? cfg.description.slice(0, 40) + (cfg.description.length > 40 ? '...' : '') : '（未填写）' }}
                </span>
                <span class="desc-toggle">{{ descExpanded[name] ? '收起 ▲' : '展开 ▼' }}</span>
              </div>
              <div v-if="descExpanded[name]" class="desc-body">
                <a-textarea
                  v-model:value="cfg.description"
                  @blur="store.saveProject()"
                  placeholder="描述此配置方案的用途、客户需求等..."
                  :rows="3"
                  :maxlength="500"
                  show-count
                />
              </div>
            </div>

            <!-- 横向分栏导航 -->
            <div class="seg-nav">
              <div
                class="seg-item"
                :class="{ active: sectionState[name] === 'hardware' }"
                @click="sectionState[name] = 'hardware'"
              >
                <span class="seg-label">硬件选配</span>
              </div>
              <div
                class="seg-item"
                :class="{ active: sectionState[name] === 'warranty' }"
                @click="sectionState[name] = 'warranty'"
              >
                <span class="seg-label">维保 / 增值服务</span>
              </div>
              <div
                class="seg-item"
                :class="{ active: sectionState[name] === 'software' }"
                @click="sectionState[name] = 'software'"
              >
                <span class="seg-label">系统 / 软件</span>
              </div>
            </div>

            <!-- 硬件选配区域 -->
            <div v-if="sectionState[name] === 'hardware'" class="section-content">
              <!-- L6 整机卡片 -->
              <div class="l6-section">
                <L6ConfigCard
                  mode="upload"
                  :base-price="cfg.l6_matched_record?.base_price"
                  :front-panel-price="cfg.l6_matched_record?.front_panel_price"
                  :rear-panel-price="cfg.l6_matched_record?.rear_panel_price"
                  :psu-price="cfg.l6_matched_record?.psu_price"
                  :custom-price="cfg.l6_custom_price"
                  :profit-margin="cfg.l6_profit_margin"
                  @configure="(config) => handleL6ConfigSave(name, config)"
                  @price-change="(price) => handleL6PriceChange(name, price)"
                  @margin-change="(margin) => handleL6MarginChange(name, margin)"
                />
              </div>

              <!-- KP 配件卡片群 -->
              <div class="glass card-kp">
                <div class="sec-head">
                  <h3 class="sec-title">Key Parts 配件 <span class="count-badge">{{ cfg.items.filter((i: any) => i.category === 'Key Parts').length }}</span></h3>
                </div>

                <div class="kp-grid">
                  <div v-for="(item, idx) in cfg.items.filter((i: any) => i.category === 'Key Parts')" :key="idx" class="glass-light kp-card">
                    <div class="kp-card-header">
                      <span class="kp-name">{{ item.part_name }}</span>
                      <span class="kp-spec" v-if="item.spec">{{ item.spec }}</span>
                    </div>

                    <div class="kp-inputs">
                      <div class="input-group">
                        <label>数量</label>
                        <a-input-number v-model:value="item.qty" size="small" style="width:100%" :min="1" @blur="store.recalculateAll()" />
                      </div>
                      <div class="input-group">
                        <label>利润率%</label>
                        <a-input-number v-model:value="item.profit_margin" size="small" style="width:100%" :min="0" @blur="store.recalculateAll()" />
                      </div>
                      <div class="input-group">
                        <label>原始单价</label>
                        <a-input-number v-model:value="item.base_price" size="small" style="width:100%" :precision="2" @blur="store.recalculateAll()" />
                      </div>
                    </div>

                    <div class="kp-footer">
                      <div class="kp-price">
                        最终售价：<span class="price-val">¥ {{ settingsStore.formatNumber(item.final_price) }}</span>
                      </div>
                      <a-button
                        size="small"
                        type="primary"
                        ghost
                        class="sync-btn"
                        :disabled="!item.match_status?.includes('变动') && !item.match_status?.includes('缺失')"
                      >
                        同步
                      </a-button>
                    </div>

                    <!-- KP 历史价格 (懒加载折叠面板) -->
                    <a-collapse class="kp-history-collapse" v-model:activeKey="item._histActiveKeys" @change="(keys: string[]) => onHistoryExpand(item, keys)">
                      <a-collapse-panel key="hist">
                        <template #header>
                          <span class="kp-hist-header">历史价格 <span v-if="item._histLoaded">({{ item._history?.length || 0 }}条)</span><span v-else>…</span></span>
                        </template>
                        <div v-if="item._histLoading" class="kp-hist-loading"><a-spin size="small" /></div>
                        <div v-else-if="item._histLoaded && item._history?.length" class="kp-hist-list">
                          <div v-for="(h, hi) in item._history" :key="hi" class="kp-hist-item">
                            <div class="kp-hist-dot"></div>
                            <div class="kp-hist-content">
                              <div class="kp-hist-row">
                                <span class="kp-hist-date">{{ h.date }}</span>
                                <span class="kp-hist-price" :class="{ usd: h.currency === 'USD' }">
                                  {{ h.currency === 'USD' ? '$' : '¥' }} {{ settingsStore.formatNumber(h.price || 0) }}
                                </span>
                              </div>
                              <div v-if="h.note" class="kp-hist-note">{{ h.note }}</div>
                            </div>
                          </div>
                        </div>
                        <div v-else class="kp-hist-empty">暂无历史价格</div>
                      </a-collapse-panel>
                    </a-collapse>
                  </div>
                </div>
              </div>
            </div>

            <!-- 维保/增值服务区域 -->
            <div v-else-if="sectionState[name] === 'warranty'" class="section-content">
              <!-- L6/KP 质保服务费独立计算 -->
              <div class="warranty-row">
                <!-- L6 质保卡片 -->
                <div class="glass-light w-card">
                  <div class="w-card-title">L6 质保服务费</div>
                  <a-textarea
                    class="w-description"
                    :value="getWarrantyDesc(cfg, 'l6')"
                    @change="(e: Event) => store.setWarrantyDescription(name, 'l6', (e.target as HTMLTextAreaElement).value)"
                    :auto-size="{ minRows: 2, maxRows: 4 }"
                    placeholder="质保描述..."
                  />
                  <div class="w-card-body">
                    <div class="w-row">
                      <span class="w-label">年限：</span>
                      <a-select
                        :value="cfg.warranty_info?.l6?.years"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => store.setWarrantyYearsL6(name, val)"
                        :options="[
                          { value: 1, label: '1 年' },
                          { value: 2, label: '2 年' },
                          { value: 3, label: '3 年' },
                          { value: 5, label: '5 年' }
                        ]"
                        allowClear
                        placeholder="选择年限"
                      />
                    </div>
                    <div class="w-row">
                      <span class="w-label">费率：</span>
                      <a-input-number
                        :value="store.getWarrantyRateL6Pct(name)"
                        :min="0"
                        :max="100"
                        :precision="2"
                        :step="0.5"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => store.setWarrantyRateL6(name, val || 0)"
                      />
                      <span class="w-unit">%</span>
                    </div>
                    <div class="w-row">
                      <span class="w-label">金额：</span>
                      <span class="w-val">¥ {{ settingsStore.formatNumber(store.calcWarrantyFeeL6(name)) }}</span>
                    </div>
                    <div class="w-btns">
                      <a-button v-if="store.getWarrantyRateL6Pct(name) > 0" type="link" size="small" danger class="w-btn" @click="store.clearWarrantyL6(name)">清零</a-button>
                    </div>
                  </div>
                </div>

                <!-- KP 质保卡片 -->
                <div class="glass-light w-card">
                  <div class="w-card-title">KP 质保服务费</div>
                  <a-textarea
                    class="w-description"
                    :value="getWarrantyDesc(cfg, 'kp')"
                    @change="(e: Event) => store.setWarrantyDescription(name, 'kp', (e.target as HTMLTextAreaElement).value)"
                    :auto-size="{ minRows: 2, maxRows: 4 }"
                    placeholder="质保描述..."
                  />
                  <div class="w-card-body">
                    <div class="w-row">
                      <span class="w-label">年限：</span>
                      <a-select
                        :value="cfg.warranty_info?.kp?.years"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => store.setWarrantyYearsKP(name, val)"
                        :options="[
                          { value: 1, label: '1 年' },
                          { value: 2, label: '2 年' },
                          { value: 3, label: '3 年' },
                          { value: 5, label: '5 年' }
                        ]"
                        allowClear
                        placeholder="选择年限"
                      />
                    </div>
                    <div class="w-row">
                      <span class="w-label">费率：</span>
                      <a-input-number
                        :value="store.getWarrantyRateKPPct(name)"
                        :min="0"
                        :max="100"
                        :precision="2"
                        :step="0.5"
                        size="small"
                        style="width: 100px"
                        @change="(val: number) => store.setWarrantyRateKP(name, val || 0)"
                      />
                      <span class="w-unit">%</span>
                    </div>
                    <div class="w-row">
                      <span class="w-label">金额：</span>
                      <span class="w-val">¥ {{ settingsStore.formatNumber(store.calcWarrantyFeeKP(name)) }}</span>
                    </div>
                    <div class="w-btns">
                      <a-button v-if="store.getWarrantyRateKPPct(name) > 0" type="link" size="small" danger class="w-btn" @click="store.clearWarrantyKP(name)">清零</a-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 系统/软件区域 -->
            <div v-else class="section-content">
              <div class="empty-placeholder glass">暂无配置内容，后续扩展</div>
            </div>
          </div>

          <!-- 右栏：配置概要 (≈28%) -->
          <div class="col-right">
            <div class="glass fin-card">
              <!-- 配置名称 -->
              <div class="fin-name">{{ name }}</div>

              <!-- 含税总价（主指标） -->
              <div class="fin-hero">
                <div class="hero-label">含税总价</div>
                <div class="hero-val">¥ {{ settingsStore.formatNumber(configTotals.totalSales) }}</div>
              </div>

              <!-- 指标行 -->
              <div class="fin-rows">
                <div class="fin-row">
                  <span class="fin-label">整机总成本</span>
                  <span class="fin-val">¥ {{ settingsStore.formatNumber(configTotals.totalCost) }}</span>
                </div>
                <div class="fin-row">
                  <span class="fin-label">总利润额</span>
                  <span class="fin-val" :class="configTotals.profit >= 0 ? 'pos' : 'neg'">¥ {{ settingsStore.formatNumber(configTotals.profit) }}</span>
                </div>
                <div class="fin-row">
                  <span class="fin-label">综合毛利率</span>
                  <span class="fin-val" :class="configTotals.marginPct >= 0 ? 'pos' : 'neg'">{{ configTotals.marginPct.toFixed(settingsStore.numberPrecision) }}%</span>
                </div>
              </div>

              <!-- 税率/汇率 设置（独立分离） -->
              <div class="fin-settings">
                <div class="fin-settings-title">税率 / 汇率</div>
                <div class="fin-setting-row">
                  <label>增值税率</label>
                  <a-input-number
                    :value="store.taxRate * 100"
                    @change="(v: number) => { store.taxRate = (v || 0) / 100; store.recalculateAll() }"
                    :min="0" :max="30" :step="1"
                    size="small"
                    style="width: 90px"
                    addon-after="%"
                  />
                </div>
                <div class="fin-setting-row">
                  <label>美元汇率</label>
                  <a-input-number
                    :value="store.exchangeRate"
                    @change="(v: number) => { store.exchangeRate = v || 7; store.recalculateAll() }"
                    :min="1" :max="20" :step="0.1"
                    size="small"
                    style="width: 90px"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- 底部垫高 -->
      <div style="height: 80px;"></div>
    </div>

    <!-- 底部悬浮操作栏 -->
    <div class="action-bar glass">
      <div class="action-bar-inner">
        <a-button @click="goBack" class="btn-ghost">{{ entryLabel || "返回" }}</a-button>

        <a-select
          v-model:value="selectedTemplateId"
          style="width: 200px"
          placeholder="选择导出模板"
        >
          <a-select-option v-for="t in templates" :key="t.id" :value="String(t.id)">
            {{ t.display_name }}{{ t.is_default ? ' (默认)' : '' }}
          </a-select-option>
        </a-select>

        <a-button @click="handlePreview" :loading="previewLoading" class="btn-ghost">预览</a-button>
        <a-button @click="store.doExport(selectedTemplateId)" :loading="exportLoading" class="btn-ghost">导出 Excel</a-button>
        <a-button type="primary" @click="handleSave()" :loading="saveLoading" class="btn-pri">保存商机</a-button>
      </div>
    </div>

    <!-- 右侧抽屉：商机文件 + 评论 -->
    <OpportunitySidebar :opportunity-id="currentOpportunityId" />

    <!-- 预览弹窗 -->
    <PreviewModal v-model:open="previewVisible" :sheets="previewSheets" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQuoteStore } from '@/store/quote'
import { useSettingsStore } from '@/store/settings'
import OpportunitySidebar from '@/components/quote/OpportunitySidebar.vue'
import PreviewModal from '@/components/quote/PreviewModal.vue'
import L6ConfigCard from '@/components/L6ConfigCard.vue'
import BomTable from '@/components/BomTable.vue'
import { message, Modal } from 'ant-design-vue'
import axios from 'axios'
import { projectApi } from '@/api'

const store = useQuoteStore()
const settingsStore = useSettingsStore()
const route = useRoute()
const router = useRouter()
const activeCfg = ref('CFG1')

// 导出模板相关
const templates = ref<any[]>([])
const selectedTemplateId = ref<string>('')
const previewLoading = ref(false)
const previewVisible = ref(false)
const previewSheets = ref<any[]>([])

// 加载导出模板列表
const loadTemplates = async () => {
  try {
    // 从Univer模板API获取模板列表
    const response = await axios.get('/api/univer-templates')
    if (response.data && response.data.templates) {
      templates.value = response.data.templates
      // 默认选中默认模板
      const defaultTemplate = response.data.templates.find((t: any) => t.is_default)
      if (defaultTemplate) {
        selectedTemplateId.value = String(defaultTemplate.id)
      }
    }
  } catch (e) {
    console.error('加载模板列表失败', e)
  }
}

// 预览处理
const handlePreview = async () => {
  if (!selectedTemplateId.value) {
    message.warning('请先选择导出模板')
    return
  }

  previewLoading.value = true
  try {
    const opportunityId = store.opportunityInfo.opportunity_id
    if (!opportunityId) {
      message.error('商机信息不完整')
      return
    }

    const data = await projectApi.previewJson(opportunityId, selectedTemplateId.value)
    previewSheets.value = data.sheets || []
    previewVisible.value = true
  } catch (e) {
    console.error('预览失败', e)
    message.error('预览失败，请重试')
  } finally {
    previewLoading.value = false
  }
}

// 质保描述默认值（从系统配置获取）
const warrantyDescDefaults = ref<{ l6: string; kp: string }>({
  l6: '',
  kp: ''
})

// 加载系统配置中的质保描述默认值
const loadWarrantyDefaults = async () => {
  try {
    const [l6Res, kpRes] = await Promise.all([
      fetch('/api/system-config/warranty_desc_l6'),
      fetch('/api/system-config/warranty_desc_kp')
    ])
    if (l6Res.ok) {
      const l6Data = await l6Res.json()
      warrantyDescDefaults.value.l6 = l6Data.value || ''
    }
    if (kpRes.ok) {
      const kpData = await kpRes.json()
      warrantyDescDefaults.value.kp = kpData.value || ''
    }
  } catch (e) {
    console.warn('Failed to load warranty defaults:', e)
  }
}

const getWarrantyDesc = (cfg: any, type: 'l6' | 'kp'): string => {
  const desc = cfg.warranty_info?.[type]?.description
  if (desc) return desc
  return warrantyDescDefaults.value[type] || ''
}
const saveLoading = ref(false)
const exportLoading = ref(false)

// 入口上下文（来自路由 query）: upload | opportunities
const entryFrom = computed(() => (route.query.from as string) || 'upload')
const entryProjectId = computed(() => (route.query.opportunityId as string) || '')
const entryLabel = computed(() => {
  if (entryFrom.value === 'opportunities') return '← 返回商机详情'
  if (entryFrom.value === 'upload') return '← 返回上传页'
  return ''
})
const goBack = () => {
  // Clean up sessionStorage to prevent stale data from being loaded next time
  sessionStorage.removeItem('quotation_data')
  if (entryFrom.value === 'opportunities' && entryProjectId.value) {
    router.push(`/opportunities/${entryProjectId.value}`)
  } else if (entryFrom.value === 'upload') {
    router.push('/upload')
  } else {
    router.push('/opportunities')
  }
}

// 当前商机 ID（用于评论关联）
// 优先用 opportunity_id，没有则用 opportunity_name，都没有则用 'default'
const currentOpportunityId = computed(() => {
  return store.opportunityInfo?.opportunity_id || store.opportunityInfo?.opportunity_name || 'default'
})

// 每个配置页的栏目状态（独立维护）
const sectionState = reactive<Record<string, string>>({})

// 每个配置页的描述框展开状态
const descExpanded = reactive<Record<string, boolean>>({})

// 配置 Tab 编辑状态（双击重命名）
const editingCfg = ref<string | null>(null)
const editingName = ref('')

// 配置 Tab 右键菜单
const contextMenu = reactive<{ visible: boolean; x: number; y: number; cfgName: string }>({
  visible: false, x: 0, y: 0, cfgName: ''
})

// 开始重命名
const startRename = (cfgName: string) => {
  editingCfg.value = cfgName
  editingName.value = cfgName
}

// 确认重命名
const confirmRename = () => {
  if (!editingCfg.value || !editingName.value.trim()) {
    editingCfg.value = null
    return
  }
  const oldName = editingCfg.value
  const newName = editingName.value.trim()

  if (oldName === newName) {
    editingCfg.value = null
    return
  }

  // 检查是否已存在
  if (store.configs[newName]) {
    message.error(`配置 "${newName}" 已存在`)
    return
  }

  // 重命名：复制数据，删除旧 key
  const oldCfg = store.configs[oldName]
  store.configs[newName] = { ...oldCfg, name: newName }
  delete store.configs[oldName]

  // 更新质保费率
  if (store.warrantyRates[oldName]) {
    store.warrantyRates[newName] = store.warrantyRates[oldName]
    delete store.warrantyRates[oldName]
  }

  // 更新栏目状态
  if (sectionState[oldName]) {
    sectionState[newName] = sectionState[oldName]
    delete sectionState[oldName]
  }

  // 更新当前激活的配置
  if (activeCfg.value === oldName) {
    activeCfg.value = newName
  }

  editingCfg.value = null
  message.success(`已重命名为 "${newName}"`)
}

// 取消重命名
const cancelRename = () => {
  editingCfg.value = null
}

// 右键菜单处理
const handleTabContextMenu = (e: MouseEvent, cfgName: string) => {
  e.preventDefault()
  contextMenu.visible = true
  contextMenu.x = e.clientX
  contextMenu.y = e.clientY
  contextMenu.cfgName = cfgName
}

// 关闭右键菜单
const closeContextMenu = () => {
  contextMenu.visible = false
}

// 删除配置
const deleteConfig = (cfgName: string) => {
  delete store.configs[cfgName]
  delete store.warrantyRates[cfgName]
  delete sectionState[cfgName]

  // 如果删除的是当前激活的配置，切换到第一个
  const remainingKeys = Object.keys(store.configs)
  if (activeCfg.value === cfgName) {
    activeCfg.value = remainingKeys[0] || ''
  }

  message.success(`已删除配置 "${cfgName}"`)
}

const deleteConfigWithConfirm = (cfgName: string) => {
  Modal.confirm({
    title: '删除配置',
    content: `确定删除配置 "${cfgName}" 吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk() {
      deleteConfig(cfgName)
    },
  })
}

// 初始化栏目状态
const initSectionState = () => {
  Object.keys(store.configs).forEach(name => {
    if (!sectionState[name]) {
      sectionState[name] = 'hardware'  // 默认显示硬件选配
    }
  })
}

// 添加配置页
const addConfig = () => {
  const existingKeys = Object.keys(store.configs)
  const nextNum = existingKeys.length + 1
  const newName = `CFG${nextNum}`
  store.configs[newName] = {
    name: newName,
    description: '',
    items: [],
    summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
    l6_matched_record: null,
    l6_custom_price: 0,
    l6_profit_margin: 10,
    warranty_info: {
      l6: { detected: false, years: null, rate: 0 },
      kp: { detected: false, years: null, rate: 0 }
    }
  }
  activeCfg.value = newName
  sectionState[newName] = 'hardware'
  message.success(`已添加配置页 ${newName}`)
}

// L6 配置保存（从内嵌 Wizard 直接触发）
const handleL6ConfigSave = (cfgName: string | number, configData: any) => {
  const cfg = store.configs[String(cfgName)]
  if (!cfg) return

  // 将四步配置的分项价格写入 l6_matched_record（卡片显示用）
  store.setL6MatchedRecord(String(cfgName), {
    ...cfg.l6_matched_record,
    base_price: configData.base_price || 0,
    front_panel_price: configData.front_panel_price || 0,
    rear_panel_price: configData.rear_panel_price || 0,
    psu_price: configData.psu_price || 0,
    price: configData.total_price || 0
  })

  // 总价作为 l6_custom_price
  store.setL6CustomPrice(String(cfgName), configData.total_price || 0, 10)

  // 存 BOM 配置详情
  store.setL6BomConfig(String(cfgName), {
    base_config: configData.base_config,
    front_panel: configData.front_panel,
    rear_panel: configData.rear_panel,
    psu: configData.psu
  })

  message.success('L6 配置已保存')
}

// L6 价格变更（从卡片直接编辑）
const handleL6PriceChange = (cfgName: string | number, price: number) => {
  const cfg = store.configs[String(cfgName)]
  if (!cfg) return
  // 使用 store 方法确保响应式更新
  store.setL6CustomPrice(String(cfgName), price, cfg.l6_profit_margin || 10)
}

// L6 利润率变更（从卡片直接编辑）
const handleL6MarginChange = (cfgName: string | number, margin: number) => {
  const cfg = store.configs[String(cfgName)]
  if (!cfg) return
  // 使用 store 方法确保响应式更新
  store.setL6CustomPrice(String(cfgName), cfg.l6_custom_price || 0, margin)
}

const handleSave = async () => {
  // Check for zero-price parts
  const zeroPriceParts = []
  for (const [cfgName, cfg] of Object.entries(store.configs)) {
    for (const item of cfg.items) {
      if (item.base_price === 0 || item.final_price === 0) {
        zeroPriceParts.push({ cfg: cfgName, part: item.part_name })
      }
    }
  }

  if (zeroPriceParts.length > 0) {
    const confirmed = await Modal.confirm({
      title: '⚠️ 存在价格为 0 的配件',
      content: `以下配件价格为 0，可能导致整机成本偏低：\n${zeroPriceParts.map(p => `• ${p.cfg}: ${p.part}`).join('\n')}\n\n确定要保存吗？`,
      okText: '继续保存',
      cancelText: '取消',
    })
    if (!confirmed) return
  }

  saveLoading.value = true
  try {
    await store.saveProject()
  } finally {
    saveLoading.value = false
  }
}

// 当前配置页的财务数据（随 tab 切换动态变化，使用 computed 确保响应式）
const configTotals = computed(() => store.getConfigTotals(activeCfg.value))

// KP 历史价格懒加载
const onHistoryExpand = async (item: any, keys: string[]) => {
  // Only load when expanded (keys contains 'hist')
  if (!keys.includes('hist')) return
  if (item._histLoaded) return  // Already loaded

  item._histLoading = true
  try {
    const model = item.spec || item.part_name
    if (!model) return
    const resp = await axios.get('/api/quote/kp/history', { params: { model } })
    item._history = resp.data || []
    item._histLoaded = true
  } catch (e) {
    item._history = []
    item._histLoaded = true
  } finally {
    item._histLoading = false
  }
}

onMounted(async () => {
  // 加载导出模板列表
  await loadTemplates()

  // 加载系统配置中的质保描述默认值
  await loadWarrantyDefaults()

  // Check routing context
  const quotationId = route.query.quotationId as string
  const mode = route.query.mode as string
  const opportunityId = route.query.opportunityId as string

  if (mode === 'create') {
    // 新建报价单：完全重置 store，确保数据隔离
    store.configs = {}
    store.configQuantities = {}
    store.configSelectedParts = {}
    store.warrantyRates = {}
    store.opportunityInfo = {
      opportunity_id: opportunityId || '',
      opportunity_name: '',
      sales_person: '',
      fae: '',
      customer_name: '',
      date: '',
      model_name: '',
      total_qty: 0,
      platform_type: '',
      chassis_form: ''
    }

    // 清除 sessionStorage
    sessionStorage.removeItem('quotation_data')

    // 初始化空白配置
    store.configs['CFG1'] = {
      name: 'CFG1',
      description: '',
      items: [],
      summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
      l6_matched_record: null,
      l6_custom_price: 0,
      l6_profit_margin: 10,
      warranty_info: {
        l6: { detected: false, years: null, rate: 0 },
        kp: { detected: false, years: null, rate: 0 }
      }
    }
    activeCfg.value = 'CFG1'
  } else if (quotationId) {
    // 从后端加载已有报价单
    try {
      const response = await axios.get(`/api/quotations/${quotationId}`)
      const quotation = response.data

      // Group items by config_name (supports multi-config quotations)
      const items = quotation.items || []
      const configs: Record<string, any> = {}
      const configDescriptions = quotation.config_descriptions || {}
      const configServerModels = quotation.config_server_models || {}
      const configQuantities = quotation.config_quantities || {}

      // 🔧 修复：先从所有数据源收集配置名，确保没有 items 的配置也能被加载
      const allConfigNames = new Set<string>()
      Object.keys(configDescriptions).forEach(name => allConfigNames.add(name))
      Object.keys(configServerModels).forEach(name => allConfigNames.add(name))
      Object.keys(configQuantities).forEach(name => allConfigNames.add(name))
      items.forEach((item: any) => allConfigNames.add(item.config_name || 'CFG1'))

      // 为每个配置创建对象
      for (const cfgName of allConfigNames) {
        configs[cfgName] = {
          name: cfgName,
          description: configDescriptions[cfgName] || '',
          server_model: configServerModels[cfgName] || '',
          items: [],
          summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
          l6_matched_record: null,
          l6_custom_price: 0,
          l6_profit_margin: 10,
          warranty_info: {
            l6: { detected: false, years: null, rate: 0 },
            kp: { detected: false, years: null, rate: 0 }
          }
        }
      }

      // 填充 items
      for (const item of items) {
        const cfgName = item.config_name || 'CFG1'
        if (configs[cfgName]) {
          configs[cfgName].items.push(item)
        }
      }

      // 🎯 Apply per-config L6 matching results from API
      const perCfgL6 = quotation.per_cfg_l6 || {}
      for (const [cfgName, l6Data] of Object.entries(perCfgL6)) {
        if (configs[cfgName]) {
          configs[cfgName].l6_matched_record = (l6Data as any).l6_matched_record || null
          configs[cfgName].l6_custom_price = (l6Data as any).l6_custom_price || 0
          configs[cfgName].l6_profit_margin = (l6Data as any).l6_profit_margin || 10
        }
      }

      // Fallback: if no per-config data, apply top-level to first config
      if (Object.keys(perCfgL6).length === 0 && quotation.l6_matched_record) {
        const cfgName = Object.keys(configs)[0] || 'CFG1'
        if (configs[cfgName]) {
          configs[cfgName].l6_matched_record = quotation.l6_matched_record
        }
      }

      // Ensure at least one config even if no items
      if (Object.keys(configs).length === 0) {
        configs['CFG1'] = {
          name: 'CFG1',
          items: [],
          summary: { l6_total: 0, kp_total: 0, warranty_total: 0, grand_total: 0 },
          l6_matched_record: quotation.l6_matched_record || null,
          warranty_info: {
            l6: { detected: false, years: null, rate: 0 },
            kp: { detected: false, years: null, rate: 0 }
          }
        }
      }

      const opportunityInfo = {
        opportunity_id: quotation.opportunity_id || opportunityId,
        opportunity_name: quotation.opportunity_name || '',
        customer_name: quotation.customer_name || '',
        quotation_id: quotation.quotation_id,
        version: quotation.version,
        fae: quotation.fae || '',
        sales_person: quotation.sales_person || '',
        date: quotation.quotation_date || quotation.date || quotation.created_at?.slice(0, 10) || '',
        model_name: quotation.model_name || '',
        l6_spec: quotation.l6_spec || '',
        description: quotation.description || quotation.l6_spec || '',
        total_qty: quotation.total_qty || 0,
      }

      // 传递 config_quantities 到 store
      store.loadData({ configs, project_info: opportunityInfo, config_quantities: configQuantities })
      message.success("已加载报价单数据")
    } catch (err) {
      console.error("加载报价单失败", err)
      message.error("加载报价单失败")
    }
  } else {
    // 从 sessionStorage 加载（上传后跳转场景，保留向后兼容）
    const dataStr = sessionStorage.getItem('quotation_data')
    if (dataStr) {
      try {
        store.loadData(JSON.parse(dataStr))
      } catch (e) {
        console.error("解析上传数据失败", e)
      }
    } else {
      console.log("📝 空工作台")
    }
  }
  initSectionState()
  store.recalculateAll()
})
</script>

<style scoped>
.workspace-page {
  position: relative;
  min-height: 100vh;
  background: var(--cpq-bg-primary);
  color: var(--cpq-text-primary);
}

/* 顶部 accent 光条 */
.workspace-page::before {
  content: '';
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--cpq-accent-primary), transparent);
  z-index: 200;
  pointer-events: none;
}

.content-inner {
  width: 100%;
  margin: 0 auto;
  padding: 24px;
}

/* ============================================
   1. 配置 Tab 栏
   ============================================ */
.cfg-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  gap: 16px;
}

.cfg-pills {
  display: flex;
  gap: 8px;
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 12px;
  padding: 6px;
}

.cfg-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--cpq-transition-fast);
  color: var(--cpq-text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.cfg-pill:hover {
  color: var(--cpq-text-primary);
  background: var(--cpq-overlay-w4);
}

.cfg-pill:hover .pill-close {
  opacity: 1;
}

.cfg-pill.active {
  background: var(--cpq-accent-primary);
  color: #06090E;
  font-weight: 600;
}

.pill-label {
  font-weight: 600;
}

.pill-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  font-size: 12px;
  line-height: 1;
  color: var(--cpq-text-muted);
  opacity: 0;
  transition: all var(--cpq-transition-fast);
  margin-left: 4px;
}

.cfg-pill.active .pill-close {
  color: #06090E;
}

.pill-close:hover {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.cfg-add-btn {
  border: 1px dashed var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: transparent !important;
  font-size: 12px;
}

.cfg-add-btn:hover {
  background: var(--cpq-overlay-a10) !important;
}

/* ============================================
   2. 右键菜单
   ============================================ */
.cfg-context-menu {
  position: fixed;
  z-index: 9999;
  background: rgba(20, 22, 26, 0.95);
  backdrop-filter: blur(12px);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 8px;
  padding: 4px;
  min-width: 140px;
  box-shadow: 0 8px 24px var(--cpq-overlay-b40);
}

.cfg-context-item {
  padding: 8px 12px;
  font-size: 13px;
  color: var(--cpq-text-primary);
  cursor: pointer;
  border-radius: 4px;
  transition: background var(--cpq-transition-fast);
}

.cfg-context-item:hover {
  background: var(--cpq-overlay-w8);
}

.cfg-context-danger:hover {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.pill-edit-input {
  background: var(--cpq-overlay-b40);
  border: 1px solid var(--cpq-accent-primary);
  color: var(--cpq-text-primary);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 13px;
  font-weight: 600;
  width: 80px;
  outline: none;
}

/* ============================================
   3. 三栏布局
   ============================================ */
.three-col-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.col-left {
  flex: 25;
  min-width: 0;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
}

.col-middle {
  flex: 53;
  min-width: 0;
}

.col-right {
  flex: 22;
  min-width: 0;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
}

/* ============================================
   4. 中栏：配置基本信息
   ============================================ */
.card-section {
  padding: 16px;
  border-radius: 14px;
  margin-bottom: 16px;
}

.basic-row {
  display: flex;
  gap: 24px;
  align-items: flex-end;
}

.basic-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.basic-field-grow {
  flex: 1;
}

.basic-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ============================================
   5. 配置描述（可折叠）
   ============================================ */
.card-desc {
  margin-bottom: 16px;
  border-radius: 14px;
  overflow: hidden;
  transition: all var(--cpq-transition-fast);
}

.desc-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  gap: 8px;
}

.desc-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-size: 14px;
}

.desc-preview {
  flex: 1;
  color: var(--cpq-text-secondary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desc-toggle {
  color: var(--cpq-accent-primary);
  font-size: 12px;
  font-weight: 500;
}

.desc-body {
  padding: 0 16px 16px;
}

.card-desc.expanded {
  box-shadow: 0 4px 12px var(--cpq-overlay-b20);
}

/* ============================================
   6. 区段导航（Segment）
   ============================================ */
.seg-nav {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
  padding: 4px;
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 10px;
  gap: 4px;
}

.seg-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-secondary);
  transition: all var(--cpq-transition-fast);
  border-radius: 6px;
}

.seg-item:hover {
  color: var(--cpq-text-primary);
}

.seg-item.active {
  color: var(--cpq-accent-primary);
  font-weight: 600;
  background: var(--cpq-overlay-a8);
}

.seg-label {
  font-size: 13px;
}

/* ============================================
   7. Section Content
   ============================================ */
.section-content {
  min-height: 200px;
}

.empty-placeholder {
  text-align: center;
  padding: 60px 20px;
  color: var(--cpq-text-secondary);
  font-size: 15px;
  border: 1px dashed var(--cpq-border-primary);
  border-radius: 12px;
}

/* ============================================
   8. L6 Section
   ============================================ */
.l6-section {
  margin-bottom: 24px;
}

.l6-section + .card-kp {
  border-top: 1px solid var(--cpq-overlay-a8);
  padding-top: 24px;
}

/* ============================================
   9. KP Section
   ============================================ */
.card-kp {
  padding: 20px;
  border-radius: 14px;
  margin-bottom: 24px;
}

.sec-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.sec-title {
  margin: 0;
  font-size: 16px;
  color: var(--cpq-text-primary) !important;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6);
  padding: 2px 8px;
  border-radius: 10px;
}

.kp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.kp-card {
  border-radius: 12px;
  padding: 16px;
  transition: all var(--cpq-transition-fast);
}

.kp-card:hover {
  transform: translateY(-2px);
}

.kp-card-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.kp-name {
  color: var(--cpq-text-primary);
  font-weight: 600;
  font-size: 14px;
}

.kp-spec {
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-weight: normal;
}

.kp-inputs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.input-group label {
  font-size: 10px;
  color: var(--cpq-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.kp-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px dashed var(--cpq-border-secondary);
}

.kp-price {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.price-val {
  color: var(--cpq-accent-primary) !important;
  font-weight: 700;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.sync-btn {
  font-size: 11px;
  padding: 0 8px;
}

/* KP 历史价格折叠面板 */
.kp-history-collapse {
  margin-top: 12px;
}

.kp-history-collapse :deep(.ant-collapse) {
  background: transparent;
  border: none;
}

.kp-history-collapse :deep(.ant-collapse-header) {
  padding: 6px 0 !important;
  font-size: 11px;
  color: var(--cpq-text-muted) !important;
}

.kp-history-collapse :deep(.ant-collapse-content-box) {
  padding: 8px 0 !important;
  background: var(--cpq-overlay-b15);
  border-radius: 6px;
  margin-top: 4px;
}

.kp-hist-header {
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.kp-hist-loading {
  text-align: center;
  padding: 12px 0;
}

.kp-hist-list {
  max-height: 160px;
  overflow-y: auto;
  padding: 0 8px;
}

.kp-hist-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--cpq-border-secondary);
}

.kp-hist-item:last-child {
  border-bottom: none;
}

.kp-hist-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--cpq-accent-primary);
  margin-top: 5px;
  flex-shrink: 0;
}

.kp-hist-content {
  flex: 1;
  min-width: 0;
}

.kp-hist-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.kp-hist-date {
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.kp-hist-price {
  font-size: 13px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  font-variant-numeric: tabular-nums;
}

.kp-hist-price.usd {
  color: var(--cpq-accent-warning);
}

.kp-hist-note {
  font-size: 10px;
  color: var(--cpq-text-disabled);
  margin-top: 2px;
}

.kp-hist-empty {
  font-size: 11px;
  color: var(--cpq-text-muted);
  text-align: center;
  padding: 12px 0;
}

/* ============================================
   10. 维保 Section
   ============================================ */
.warranty-row {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
}

.w-card {
  flex: 1;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.w-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--cpq-accent-primary);
}

.w-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--cpq-border-secondary);
  width: 100%;
}

.w-description {
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin-bottom: 16px;
  line-height: 1.6;
  padding: 0 8px;
}

.w-card-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.w-row {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
}

.w-label {
  color: var(--cpq-text-muted);
  font-size: 12px;
  min-width: 50px;
  text-align: right;
}

.w-unit {
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.w-val {
  color: var(--cpq-accent-primary) !important;
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.w-btns {
  display: flex;
  justify-content: center;
  margin-top: 6px;
  min-height: 28px;
}

.w-btn {
  align-self: center;
  margin-top: 6px;
}

/* ============================================
   11. 右栏：财务面板
   ============================================ */
.fin-card {
  border-radius: 14px;
  overflow: hidden;
  padding: 0;
}

.fin-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  padding: 16px 20px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
}

.fin-hero {
  padding: 20px;
}

.hero-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.hero-val {
  font-size: 28px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.fin-rows {
  padding: 0 20px 16px;
}

.fin-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--cpq-overlay-w3);
}

.fin-row:last-child {
  border-bottom: none;
}

.fin-label {
  width: 110px;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--cpq-text-muted);
  text-align: right;
  padding-right: 16px;
}

.fin-val {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-variant-numeric: tabular-nums;
}

.fin-val.pos {
  color: var(--cpq-accent-primary);
}

.fin-val.neg {
  color: var(--cpq-accent-danger);
}

.fin-settings {
  padding: 16px 20px;
  border-top: 1px solid var(--cpq-overlay-w6);
}

.fin-settings-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-secondary);
  margin-bottom: 12px;
}

.fin-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.fin-setting-row:last-child {
  margin-bottom: 0;
}

.fin-setting-row label {
  font-size: 12px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
}

/* ============================================
   12. 底部操作栏
   ============================================ */
.action-bar {
  position: sticky;
  bottom: 0;
  padding: 16px 24px;
  z-index: 99;
}

.action-bar-inner {
  width: 100%;
  margin: 0 auto;
  display: flex;
  justify-content: center;
  gap: 16px;
}

.btn-ghost {
  background: transparent !important;
  border: 1px solid var(--cpq-overlay-w20) !important;
  color: var(--cpq-text-primary) !important;
  font-size: 13px;
  padding: 8px 20px;
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.btn-ghost:hover {
  border-color: var(--cpq-accent-primary) !important;
  color: var(--cpq-accent-primary) !important;
  background: var(--cpq-overlay-a5) !important;
}

.btn-pri {
  background: var(--cpq-accent-primary) !important;
  border: 1px solid var(--cpq-accent-primary) !important;
  color: #06090E !important;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 24px;
  border-radius: 8px;
  transition: all var(--cpq-transition-fast);
}

.btn-pri:hover {
  box-shadow: 0 0 20px var(--cpq-overlay-a40);
}

/* ============================================
   13. Ant Design 暗色输入覆盖
   ============================================ */
:deep(.ant-input-number),
:deep(.ant-input),
:deep(.ant-select-selector) {
  background: var(--cpq-overlay-b30) !important;
  border: 1px solid var(--cpq-overlay-w10) !important;
  color: var(--cpq-text-primary) !important;
  border-radius: 6px;
  transition: all var(--cpq-transition-fast);
}

:deep(.ant-input-number-input),
:deep(.ant-input) {
  color: var(--cpq-text-primary) !important;
  background: transparent !important;
}

:deep(.ant-input-number-focused),
:deep(.ant-input-focused),
:deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a15) !important;
}

:deep(.ant-input-number-handler-wrap) {
  background: var(--cpq-overlay-w4) !important;
  border-left: 1px solid var(--cpq-overlay-w6) !important;
}

:deep(.ant-input-number-handler-up-inner),
:deep(.ant-input-number-handler-down-inner) {
  color: var(--cpq-text-secondary) !important;
}
</style>
