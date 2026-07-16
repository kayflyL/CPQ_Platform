<template>
  <div class="l6-pricing-page">
    <div class="page-header">
      <h1>机箱</h1>
      <p class="subtitle">管理机箱配置、面板选项和电源方案</p>
    </div>

    <a-layout class="main-layout">
      <a-layout-sider width="180" theme="light" class="menu-sider">
        <a-menu
          v-model:selectedKeys="selectedMenuKeys"
          mode="inline"
          @click="onMenuClick"
        >
          <a-menu-item key="config-tool">机箱配置</a-menu-item>
          <a-sub-menu key="chassis-library" title="机箱配套库">
            <a-menu-item key="base-config">基准底盘</a-menu-item>
            <a-menu-item key="front-panel">前面板线缆</a-menu-item>
            <a-menu-item key="rear-panel">后置IO扩展模组</a-menu-item>
            <a-menu-item key="psu">电源</a-menu-item>
          </a-sub-menu>
          <a-menu-item key="price-records">整机价格记录</a-menu-item>
        </a-menu>
      </a-layout-sider>

      <a-layout-content class="main-content">
        <!-- Panel 1: 机箱配置工具 -->
        <div v-if="activeTab === 'config-tool'" class="content-panel">
          <div class="config-tool-workflow">
            <L6ConfigWizard @save="handleWizardSave" />
          </div>
        </div>

        <!-- Panel 2: 基准底盘 -->
        <div v-if="activeTab === 'base-config'" class="content-panel">
          <div class="library-panel">
            <div class="panel-header">
              <h3>基准配置管理</h3>
              <a-button type="primary" @click="openBaseConfigModal">新增配置</a-button>
            </div>
            <a-table
              :columns="baseConfigLibraryColumns"
              :data-source="baseConfigs"
              :loading="loadingBaseConfigs"
              row-key="config_id"
              :pagination="false"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'action'">
                  <a-space>
                    <a @click="editBaseConfig(record)">编辑</a>
                    <a @click="viewBaseConfigParts(record)">组件</a>
                    <a-popconfirm title="确定删除？" @confirm="deleteBaseConfig(record.config_id)">
                      <a style="color: #ff4d4f;">删除</a>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </div>
        </div>

        <!-- Panel 3: 前面板线缆 -->
        <div v-if="activeTab === 'front-panel'" class="content-panel">
          <div class="library-panel">
            <div class="panel-header">
              <h3>前面板线缆管理</h3>
              <a-button type="primary" @click="openFrontPanelModal">新增线缆</a-button>
            </div>
            <a-table
              :columns="frontPanelLibraryColumns"
              :data-source="frontPanelItems"
              :loading="loadingFrontPanel"
              row-key="item_id"
              :pagination="false"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'applicable_chassis'">
                  {{ formatChassisTypes(record.applicable_chassis) }}
                </template>
                <template v-if="column.key === 'applicable_drive_bays'">
                  {{ formatDriveBays(record.applicable_drive_bays) }}
                </template>
                <template v-if="column.key === 'applicable_backplane'">
                  {{ formatBackplaneTypes(record.applicable_backplane) }}
                </template>
                <template v-if="column.key === 'action'">
                  <a-space>
                    <a @click="editFrontPanel(record)">编辑</a>
                    <a-popconfirm title="确定删除？" @confirm="deleteFrontPanel(record.item_id)">
                      <a style="color: #ff4d4f;">删除</a>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </div>
        </div>

        <!-- Panel 4: 后置IO扩展模组 -->
        <div v-if="activeTab === 'rear-panel'" class="content-panel">
          <div class="library-panel">
            <div class="panel-header">
              <h3>后面板选项管理</h3>
              <a-button type="primary" @click="openRearPanelModal">新增选项</a-button>
            </div>
            <a-table
              :columns="rearPanelLibraryColumns"
              :data-source="rearPanelItems"
              :loading="loadingRearPanel"
              row-key="item_id"
              :pagination="false"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'applicable_chassis'">
                  {{ formatChassisTypes(record.applicable_chassis) }}
                </template>
                <template v-if="column.key === 'applicable_backplane'">
                  {{ formatBackplaneTypes(record.applicable_backplane) }}
                </template>
                <template v-if="column.key === 'action'">
                  <a-space>
                    <a @click="editRearPanel(record)">编辑</a>
                    <a-popconfirm title="确定删除？" @confirm="deleteRearPanel(record.item_id)">
                      <a style="color: #ff4d4f;">删除</a>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </div>
        </div>

        <!-- Panel 5: 电源 -->
        <div v-if="activeTab === 'psu'" class="content-panel">
          <div class="library-panel">
            <div class="panel-header">
              <h3>电源方案管理</h3>
              <a-button type="primary" @click="openPsuModal">新增电源</a-button>
            </div>
            <a-table
              :columns="psuLibraryColumns"
              :data-source="psuOptions"
              :loading="loadingPsu"
              row-key="psu_id"
              :pagination="false"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'applicable_chassis'">
                  {{ formatChassisTypes(record.applicable_chassis) }}
                </template>
                <template v-if="column.key === 'action'">
                  <a-space>
                    <a @click="editPsu(record)">编辑</a>
                    <a-popconfirm title="确定删除？" @confirm="deletePsu(record.psu_id)">
                      <a style="color: #ff4d4f;">删除</a>
                    </a-popconfirm>
                  </a-space>
                </template>
              </template>
            </a-table>
          </div>
        </div>

        <!-- Panel 6: 整机价格记录 -->
        <div v-if="activeTab === 'price-records'" class="content-panel">
          <div class="price-records-panel">
            <!-- 工具栏 -->
            <div class="panel-header">
              <h3>L6 整机历史报价</h3>
              <a-space>
                <a-input
                  v-model:value="priceSearchText"
                  placeholder="搜索机型、主板、机箱..."
                  style="width: 240px"
                  @pressEnter="loadPriceRecords"
                  allow-clear
                />
                <a-button @click="showPriceFilter = !showPriceFilter">
                  规格筛选
                </a-button>
                <a-button type="primary" @click="openPriceRecordModal">新增记录</a-button>
              </a-space>
            </div>

            <!-- 筛选面板 -->
            <div v-if="showPriceFilter" class="filter-wrapper">
              <L6SpecFilter :records="allPriceRecords" @filter-change="onPriceFilterChange" />
            </div>

            <!-- 分组卡片列表 -->
            <div v-if="priceGroups.length > 0" class="price-groups">
              <div v-for="group in priceGroups" :key="group.model" class="price-group">
                <div class="group-header" @click="togglePriceGroup(group.model)">
                  <div class="group-info">
                    <span class="expand-icon" :class="{ 'expanded': expandedPriceModels.has(group.model) }">▸</span>
                    <span class="model-title">{{ group.model }}</span>
                    <a-tag color="blue">{{ group.count }} 个配置</a-tag>
                  </div>
                  <div class="group-price-range">
                    <template v-if="group.price_min === group.price_max">
                      <span>¥ {{ formatPrice(group.price_min) }}</span>
                    </template>
                    <template v-else>
                      <span>¥ {{ formatPrice(group.price_min) }} ~ {{ formatPrice(group.price_max) }}</span>
                    </template>
                  </div>
                </div>

                <div class="records-wrapper" :class="{ 'expanded': expandedPriceModels.has(group.model) }">
                  <div class="records-grid">
                    <template v-for="record in group.records" :key="record.id">
                      <L6RecordCard
                        :record="record"
                        :show-actions="true"
                        :matched="isPriceRecordMatched(record)"
                        @edit="openPriceEditModal(record)"
                        @delete="deletePriceRecord(record.id)"
                      />
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <a-empty v-else description="暂无价格记录" />
          </div>
        </div>
      </a-layout-content>
    </a-layout>

    <!-- 基准配置编辑弹窗 -->
    <a-modal
      v-model:open="baseConfigModalVisible"
      :title="editingBaseConfig ? '编辑基准配置' : '新增基准配置'"
      @ok="saveBaseConfig"
      :confirm-loading="savingBaseConfig"
      width="600px"
    >
      <a-form :model="baseConfigForm" layout="vertical">
        <a-form-item label="机箱" required>
          <a-select v-model:value="baseConfigForm.chassis" placeholder="选择机箱形态" allow-clear>
            <a-select-option value="2U">2U</a-select-option>
            <a-select-option value="4U">4U</a-select-option>
            <a-select-option value="4.5U">4.5U</a-select-option>
            <a-select-option value="5U">5U</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="系列" required>
          <a-select v-model:value="baseConfigForm.chassis_series" placeholder="选择系列" allow-clear>
            <a-select-option value="Polaris">Polaris</a-select-option>
            <a-select-option value="Orion">Orion</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="盘位数量">
          <a-select v-model:value="baseConfigForm.drive_bays" placeholder="选择盘位数量" allow-clear>
            <a-select-option value="12">12</a-select-option>
            <a-select-option value="25">25</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="背板类型">
          <a-select v-model:value="baseConfigForm.backplane_type" placeholder="选择背板类型" allow-clear>
            <a-select-option value="Tri-Mode">Tri-Mode (三模)</a-select-option>
            <a-select-option value="Pass-through">Pass-through (直通)</a-select-option>
            <a-select-option value="PCIe Switch">PCIe Switch (交换)</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="baseConfigForm.description" :rows="3" />
        </a-form-item>
        <a-form-item label="不包含项">
          <a-input v-model:value="baseConfigForm.excludes" placeholder="如：硬盘、内存" />
        </a-form-item>
        <a-form-item label="基准价格">
          <a-input-number v-model:value="baseConfigForm.base_price" :min="0" :step="0.01" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="baseConfigForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 基准配置组件管理弹窗 -->
    <a-modal
      v-model:open="baseConfigPartsModalVisible"
      :title="`组件管理 - ${selectedBaseConfigForParts?.chassis || ''} ${selectedBaseConfigForParts?.chassis_series || ''} ${selectedBaseConfigForParts?.description || ''}`"
      width="800px"
      :footer="null"
    >
      <div style="margin-bottom: 16px;">
        <a-button type="primary" size="small" @click="openBaseConfigPartModal">新增组件</a-button>
      </div>
      <a-table
        :columns="baseConfigPartColumns"
        :data-source="baseConfigParts"
        :loading="loadingBaseConfigParts"
        row-key="part_id"
        :pagination="false"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <a-space>
              <a @click="editBaseConfigPart(record)">编辑</a>
              <a-popconfirm title="确定删除？" @confirm="deleteBaseConfigPart(record.part_id)">
                <a style="color: #ff4d4f;">删除</a>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-modal>

    <!-- 基准配置组件编辑弹窗 -->
    <a-modal
      v-model:open="baseConfigPartModalVisible"
      :title="editingBaseConfigPart ? '编辑组件' : '新增组件'"
      @ok="saveBaseConfigPart"
      :confirm-loading="savingBaseConfigPart"
      width="600px"
    >
      <a-form :model="baseConfigPartForm" layout="vertical">
        <a-form-item label="料号">
          <a-input v-model:value="baseConfigPartForm.pn" placeholder="如：S.E.M.0000351" />
        </a-form-item>
        <a-form-item label="部件名称" required>
          <a-input v-model:value="baseConfigPartForm.part_name" placeholder="如：Chassis" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="baseConfigPartForm.description" />
        </a-form-item>
        <a-form-item label="单价">
          <a-input-number v-model:value="baseConfigPartForm.unit_price" :min="0" :step="0.01" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="数量">
          <a-input-number v-model:value="baseConfigPartForm.quantity" :min="1" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="备注">
          <a-input v-model:value="baseConfigPartForm.note" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="baseConfigPartForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 前面板线缆编辑弹窗 -->
    <a-modal
      v-model:open="frontPanelModalVisible"
      :title="editingFrontPanel ? '编辑线缆' : '新增线缆'"
      @ok="saveFrontPanel"
      :confirm-loading="savingFrontPanel"
      width="600px"
    >
      <a-form :model="frontPanelForm" layout="vertical">
        <a-form-item label="线缆类型" required>
          <a-select v-model:value="frontPanelForm.cable_type">
            <a-select-option value="SATA">SATA</a-select-option>
            <a-select-option value="SAS">SAS</a-select-option>
            <a-select-option value="NVMe">NVMe</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="料号">
          <a-input v-model:value="frontPanelForm.pn" />
        </a-form-item>
        <a-form-item label="部件名称" required>
          <a-input v-model:value="frontPanelForm.part_name" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="frontPanelForm.description" />
        </a-form-item>
        <a-form-item label="单价">
          <a-input-number v-model:value="frontPanelForm.unit_price" :min="0" :step="0.01" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="每组盘数">
          <a-input-number v-model:value="frontPanelForm.group_size" :min="1" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="适用机箱形态">
          <a-select
            v-model:value="frontPanelForm.applicable_chassis"
            mode="multiple"
            placeholder="选择适用的机箱形态（2U/4U/4.5U/5U）"
            style="width: 100%;"
          >
            <a-select-option value="2U">2U</a-select-option>
            <a-select-option value="4U">4U</a-select-option>
            <a-select-option value="4.5U">4.5U</a-select-option>
            <a-select-option value="5U">5U</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="适用盘位">
          <a-select
            v-model:value="frontPanelForm.applicable_drive_bays"
            mode="multiple"
            placeholder="选择适用的盘位数量"
            style="width: 100%;"
          >
            <a-select-option value="12">12</a-select-option>
            <a-select-option value="25">25</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="适用背板类型">
          <a-select
            v-model:value="frontPanelForm.applicable_backplane"
            mode="multiple"
            placeholder="选择适用的背板类型"
            style="width: 100%;"
          >
            <a-select-option value="Tri-Mode">Tri-Mode (三模)</a-select-option>
            <a-select-option value="Pass-through">Pass-through (直通)</a-select-option>
            <a-select-option value="PCIe Switch">PCIe Switch (交换)</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="备注">
          <a-input v-model:value="frontPanelForm.note" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="frontPanelForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 后面板选项编辑弹窗 -->
    <a-modal
      v-model:open="rearPanelModalVisible"
      :title="editingRearPanel ? '编辑选项' : '新增选项'"
      @ok="saveRearPanel"
      :confirm-loading="savingRearPanel"
      width="600px"
    >
      <a-form :model="rearPanelForm" layout="vertical">
        <a-form-item label="IO槽位">
          <a-select v-model:value="rearPanelForm.io_slot" allow-clear>
            <a-select-option value="IO1">IO1</a-select-option>
            <a-select-option value="IO2">IO2</a-select-option>
            <a-select-option value="IO3">IO3</a-select-option>
            <a-select-option value="IO4">IO4</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="选项类型" required>
          <a-select v-model:value="rearPanelForm.option_type">
            <a-select-option value="Riser">Riser</a-select-option>
            <a-select-option value="NVMe模组">NVMe模组</a-select-option>
            <a-select-option value="SATA模组">SATA模组</a-select-option>
            <a-select-option value="OCP">OCP</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="料号">
          <a-input v-model:value="rearPanelForm.pn" />
        </a-form-item>
        <a-form-item label="部件名称" required>
          <a-input v-model:value="rearPanelForm.part_name" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="rearPanelForm.description" />
        </a-form-item>
        <a-form-item label="单价">
          <a-input-number v-model:value="rearPanelForm.unit_price" :min="0" :step="0.01" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="数量">
          <a-input-number v-model:value="rearPanelForm.quantity" :min="1" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="适用机箱形态">
          <a-select
            v-model:value="rearPanelForm.applicable_chassis"
            mode="multiple"
            placeholder="选择适用的机箱形态（2U/4U/4.5U/5U）"
            style="width: 100%;"
          >
            <a-select-option value="2U">2U</a-select-option>
            <a-select-option value="4U">4U</a-select-option>
            <a-select-option value="4.5U">4.5U</a-select-option>
            <a-select-option value="5U">5U</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="适用背板类型">
          <a-select
            v-model:value="rearPanelForm.applicable_backplane"
            mode="multiple"
            placeholder="选择适用的背板类型"
            style="width: 100%;"
          >
            <a-select-option value="Tri-Mode">Tri-Mode (三模)</a-select-option>
            <a-select-option value="Pass-through">Pass-through (直通)</a-select-option>
            <a-select-option value="PCIe Switch">PCIe Switch (交换)</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="备注">
          <a-input v-model:value="rearPanelForm.note" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="rearPanelForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 电源编辑弹窗 -->
    <a-modal
      v-model:open="psuModalVisible"
      :title="editingPsu ? '编辑电源' : '新增电源'"
      @ok="savePsu"
      :confirm-loading="savingPsu"
      width="600px"
    >
      <a-form :model="psuForm" layout="vertical">
        <a-form-item label="功率" required>
          <a-input v-model:value="psuForm.wattage" placeholder="如：1300W" />
        </a-form-item>
        <a-form-item label="料号">
          <a-input v-model:value="psuForm.pn" />
        </a-form-item>
        <a-form-item label="部件名称" required>
          <a-input v-model:value="psuForm.part_name" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="psuForm.description" />
        </a-form-item>
        <a-form-item label="单价">
          <a-input-number v-model:value="psuForm.unit_price" :min="0" :step="0.01" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="适用机箱形态">
          <a-select
            v-model:value="psuForm.applicable_chassis"
            mode="multiple"
            placeholder="选择适用的机箱形态（2U/4U/4.5U/5U）"
            style="width: 100%;"
          >
            <a-select-option value="2U">2U</a-select-option>
            <a-select-option value="4U">4U</a-select-option>
            <a-select-option value="4.5U">4.5U</a-select-option>
            <a-select-option value="5U">5U</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="备注">
          <a-input v-model:value="psuForm.note" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="psuForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import L6RecordCard from '@/components/L6RecordCard.vue'
import L6SpecFilter from '@/components/L6SpecFilter.vue'
import L6ConfigWizard from '@/components/L6ConfigWizard.vue'
import { useL6ChassisConfig } from '@/composables/useL6ChassisConfig'

// Tab 状态
const activeTab = ref('config-tool')
const selectedMenuKeys = ref(['config-tool'])

const onMenuClick = ({ key }: { key: string }) => {
  activeTab.value = key
}

// 使用 composable 管理数据加载（仅保留管理页面需要的部分）
const {
  baseConfigs,
  frontPanelItems,
  rearPanelItems,
  psuOptions,
  loadBaseConfigs,
  loadFrontPanelItems,
  loadRearPanelItems,
  loadPsuOptions
} = useL6ChassisConfig()

const loadingBaseConfigs = ref(false)
const loadingFrontPanel = ref(false)
const loadingRearPanel = ref(false)
const loadingPsu = ref(false)

// 基准配置 CRUD
const baseConfigModalVisible = ref(false)
const editingBaseConfig = ref<any>(null)
const savingBaseConfig = ref(false)
const baseConfigForm = ref({
  config_id: null,
  chassis: '',
  chassis_series: '',
  drive_bays: '',
  backplane_type: '',
  base_price: 0,
  description: '',
  excludes: '',
  sort_order: 0
})

// 基准配置组件
const baseConfigPartsModalVisible = ref(false)
const selectedBaseConfigForParts = ref<any>(null)
const baseConfigParts = ref<any[]>([])
const loadingBaseConfigParts = ref(false)

const baseConfigPartModalVisible = ref(false)
const editingBaseConfigPart = ref<any>(null)
const savingBaseConfigPart = ref(false)
const baseConfigPartForm = ref({
  config_id: 0,
  pn: '',
  part_name: '',
  description: '',
  unit_price: 0,
  quantity: 1,
  note: '',
  sort_order: 0
})

// 前面板表单
const frontPanelModalVisible = ref(false)
const editingFrontPanel = ref<any>(null)
const savingFrontPanel = ref(false)
const frontPanelForm = ref({
  cable_type: 'SATA',
  pn: '',
  part_name: '',
  description: '',
  unit_price: 0,
  group_size: 1,
  applicable_chassis: [] as string[],
  applicable_drive_bays: [] as string[],
  applicable_backplane: [] as string[],
  note: '',
  sort_order: 0
})

// 后面板表单
const rearPanelModalVisible = ref(false)
const editingRearPanel = ref<any>(null)
const savingRearPanel = ref(false)
const rearPanelForm = ref({
  io_slot: '',
  option_type: 'Riser',
  pn: '',
  part_name: '',
  description: '',
  unit_price: 0,
  quantity: 1,
  applicable_chassis: [] as string[],
  applicable_backplane: [] as string[],
  note: '',
  sort_order: 0
})

// 电源表单
const psuModalVisible = ref(false)
const editingPsu = ref<any>(null)
const savingPsu = ref(false)
const psuForm = ref({
  wattage: '',
  pn: '',
  part_name: '',
  description: '',
  unit_price: 0,
  applicable_chassis: [] as string[],
  note: '',
  sort_order: 0
})

// 表格列定义
const baseConfigLibraryColumns = [
  { title: '机箱', dataIndex: 'chassis', key: 'chassis' },
  { title: '系列', dataIndex: 'chassis_series', key: 'chassis_series' },
  { title: '盘位', dataIndex: 'drive_bays', key: 'drive_bays' },
  { title: '背板类型', dataIndex: 'backplane_type', key: 'backplane_type' },
  { title: '基准价格', dataIndex: 'base_price', key: 'base_price', customRender: ({ text }: any) => `¥${text?.toFixed(2)}` },
  { title: '操作', key: 'action', width: 180 }
]

const frontPanelLibraryColumns = [
  { title: '线缆类型', dataIndex: 'cable_type', key: 'cable_type' },
  { title: '部件名称', dataIndex: 'part_name', key: 'part_name' },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', customRender: ({ text }: any) => `¥${text?.toFixed(2)}` },
  { title: '适用机箱形态', key: 'applicable_chassis', width: 150 },
  { title: '适用盘位', key: 'applicable_drive_bays', width: 120 },
  { title: '适用背板', key: 'applicable_backplane', width: 150 },
  { title: '操作', key: 'action', width: 120 }
]

const rearPanelLibraryColumns = [
  { title: 'IO槽位', dataIndex: 'io_slot', key: 'io_slot' },
  { title: '选项类型', dataIndex: 'option_type', key: 'option_type' },
  { title: '部件名称', dataIndex: 'part_name', key: 'part_name' },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', customRender: ({ text }: any) => `¥${text?.toFixed(2)}` },
  { title: '适用机箱', key: 'applicable_chassis', width: 150 },
  { title: '适用背板', key: 'applicable_backplane', width: 150 },
  { title: '操作', key: 'action', width: 120 }
]

const psuLibraryColumns = [
  { title: '功率', dataIndex: 'wattage', key: 'wattage' },
  { title: '部件名称', dataIndex: 'part_name', key: 'part_name' },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', customRender: ({ text }: any) => `¥${text?.toFixed(2)}` },
  { title: '适用机箱形态', key: 'applicable_chassis', width: 150 },
  { title: '操作', key: 'action', width: 120 }
]

const baseConfigPartColumns = [
  { title: '料号', dataIndex: 'pn', key: 'pn' },
  { title: '部件名称', dataIndex: 'part_name', key: 'part_name' },
  { title: '单价', dataIndex: 'unit_price', key: 'unit_price', customRender: ({ text }: any) => `¥${text?.toFixed(2)}` },
  { title: '数量', dataIndex: 'quantity', key: 'quantity' },
  { title: '操作', key: 'action', width: 120 }
]

// Wizard 保存处理
const handleWizardSave = async (config: any) => {
  try {
    await axios.post('/api/l6-chassis/save-config', {
      base_config_id: config.base_config?.config_id,
      front_panel_id: config.front_panel?.item_id,
      rear_panel_id: config.rear_panel?.item_id,
      psu_id: config.psu?.psu_id,
      base_price: config.base_price,
      front_panel_price: config.front_panel_price,
      rear_panel_price: config.rear_panel_price,
      psu_price: config.psu_price,
      total_price: config.total_price
    })
    message.success('配置已保存')
  } catch (e: any) {
    console.error('保存配置失败:', e)
    message.error('保存失败')
  }
}

// 基准配置 CRUD
const openBaseConfigModal = () => {
  editingBaseConfig.value = null
  baseConfigForm.value = {
    config_id: null,
    chassis: '',
    chassis_series: '',
    description: '',
    excludes: '',
    base_price: 0,
    drive_bays: '',
    backplane_type: '',
    sort_order: 0
  }
  baseConfigModalVisible.value = true
}

const editBaseConfig = (config: any) => {
  editingBaseConfig.value = config
  baseConfigForm.value = { ...config }
  baseConfigModalVisible.value = true
}

const saveBaseConfig = async () => {
  if (!baseConfigForm.value.chassis || !baseConfigForm.value.chassis_series) {
    message.warning('请填写必填字段')
    return
  }

  savingBaseConfig.value = true
  try {
    if (editingBaseConfig.value) {
      await axios.put(`/api/l6-chassis/base-configs/${editingBaseConfig.value.config_id}`, baseConfigForm.value)
      message.success('更新成功')
    } else {
      await axios.post('/api/l6-chassis/base-configs', baseConfigForm.value)
      message.success('创建成功')
    }
    baseConfigModalVisible.value = false
    loadBaseConfigs()
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    savingBaseConfig.value = false
  }
}

const deleteBaseConfig = async (configId: number) => {
  try {
    await axios.delete(`/api/l6-chassis/base-configs/${configId}`)
    message.success('删除成功')
    loadBaseConfigs()
  } catch (e: any) {
    message.error('删除失败')
  }
}

const viewBaseConfigParts = async (config: any) => {
  selectedBaseConfigForParts.value = config
  baseConfigPartsModalVisible.value = true
  await loadBaseConfigParts(config.config_id)
}

const loadBaseConfigParts = async (configId: number) => {
  loadingBaseConfigParts.value = true
  try {
    const res = await axios.get(`/api/l6-chassis/base-configs/${configId}/parts`)
    baseConfigParts.value = res.data.parts || []
  } catch (e: any) {
    message.error('加载组件失败')
  } finally {
    loadingBaseConfigParts.value = false
  }
}

const openBaseConfigPartModal = () => {
  editingBaseConfigPart.value = null
  baseConfigPartForm.value = {
    config_id: selectedBaseConfigForParts.value?.config_id || 0,
    pn: '',
    part_name: '',
    description: '',
    unit_price: 0,
    quantity: 1,
    note: '',
    sort_order: 0
  }
  baseConfigPartModalVisible.value = true
}

const editBaseConfigPart = (part: any) => {
  editingBaseConfigPart.value = part
  baseConfigPartForm.value = { ...part }
  baseConfigPartModalVisible.value = true
}

const saveBaseConfigPart = async () => {
  if (!baseConfigPartForm.value.part_name) {
    message.warning('请填写部件名称')
    return
  }

  savingBaseConfigPart.value = true
  try {
    if (editingBaseConfigPart.value) {
      await axios.put(`/api/l6-chassis/base-config-parts/${editingBaseConfigPart.value.part_id}`, baseConfigPartForm.value)
      message.success('更新成功')
    } else {
      await axios.post('/api/l6-chassis/base-config-parts', baseConfigPartForm.value)
      message.success('创建成功')
    }
    baseConfigPartModalVisible.value = false
    if (selectedBaseConfigForParts.value) {
      await loadBaseConfigParts(selectedBaseConfigForParts.value.config_id)
    }
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    savingBaseConfigPart.value = false
  }
}

const deleteBaseConfigPart = async (partId: number) => {
  try {
    await axios.delete(`/api/l6-chassis/base-config-parts/${partId}`)
    message.success('删除成功')
    if (selectedBaseConfigForParts.value) {
      await loadBaseConfigParts(selectedBaseConfigForParts.value.config_id)
    }
  } catch (e: any) {
    message.error('删除失败')
  }
}

// 前面板 CRUD
const openFrontPanelModal = () => {
  editingFrontPanel.value = null
  frontPanelForm.value = {
    cable_type: 'SATA',
    pn: '',
    part_name: '',
    description: '',
    unit_price: 0,
    group_size: 1,
    applicable_chassis: [],
    applicable_drive_bays: [],
    applicable_backplane: [],
    note: '',
    sort_order: 0
  }
  frontPanelModalVisible.value = true
}

const editFrontPanel = (item: any) => {
  editingFrontPanel.value = item
  frontPanelForm.value = {
    ...item,
    applicable_chassis: JSON.parse(item.applicable_chassis || '[]'),
    applicable_drive_bays: JSON.parse(item.applicable_drive_bays || '[]'),
    applicable_backplane: JSON.parse(item.applicable_backplane || '[]')
  }
  frontPanelModalVisible.value = true
}

const saveFrontPanel = async () => {
  if (!frontPanelForm.value.part_name) {
    message.warning('请填写部件名称')
    return
  }

  savingFrontPanel.value = true
  try {
    const data = {
      ...frontPanelForm.value,
      applicable_chassis: JSON.stringify(frontPanelForm.value.applicable_chassis),
      applicable_drive_bays: JSON.stringify(frontPanelForm.value.applicable_drive_bays),
      applicable_backplane: JSON.stringify(frontPanelForm.value.applicable_backplane)
    }
    if (editingFrontPanel.value) {
      await axios.put(`/api/l6-chassis/front-panel/${editingFrontPanel.value.item_id}`, data)
      message.success('更新成功')
    } else {
      await axios.post('/api/l6-chassis/front-panel', data)
      message.success('创建成功')
    }
    frontPanelModalVisible.value = false
    loadFrontPanelItems()
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    savingFrontPanel.value = false
  }
}

const deleteFrontPanel = async (itemId: number) => {
  try {
    await axios.delete(`/api/l6-chassis/front-panel/${itemId}`)
    message.success('删除成功')
    loadFrontPanelItems()
  } catch (e: any) {
    message.error('删除失败')
  }
}

// 后面板 CRUD
const openRearPanelModal = () => {
  editingRearPanel.value = null
  rearPanelForm.value = {
    io_slot: '',
    option_type: 'Riser',
    pn: '',
    part_name: '',
    description: '',
    unit_price: 0,
    quantity: 1,
    applicable_chassis: [],
    applicable_backplane: [],
    note: '',
    sort_order: 0
  }
  rearPanelModalVisible.value = true
}

const editRearPanel = (item: any) => {
  editingRearPanel.value = item
  rearPanelForm.value = {
    ...item,
    applicable_chassis: JSON.parse(item.applicable_chassis || '[]'),
    applicable_backplane: JSON.parse(item.applicable_backplane || '[]')
  }
  rearPanelModalVisible.value = true
}

const saveRearPanel = async () => {
  if (!rearPanelForm.value.part_name) {
    message.warning('请填写部件名称')
    return
  }

  savingRearPanel.value = true
  try {
    const data = {
      ...rearPanelForm.value,
      applicable_chassis: JSON.stringify(rearPanelForm.value.applicable_chassis),
      applicable_backplane: JSON.stringify(rearPanelForm.value.applicable_backplane)
    }
    if (editingRearPanel.value) {
      await axios.put(`/api/l6-chassis/rear-panel/${editingRearPanel.value.item_id}`, data)
      message.success('更新成功')
    } else {
      await axios.post('/api/l6-chassis/rear-panel', data)
      message.success('创建成功')
    }
    rearPanelModalVisible.value = false
    loadRearPanelItems()
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    savingRearPanel.value = false
  }
}

const deleteRearPanel = async (itemId: number) => {
  try {
    await axios.delete(`/api/l6-chassis/rear-panel/${itemId}`)
    message.success('删除成功')
    loadRearPanelItems()
  } catch (e: any) {
    message.error('删除失败')
  }
}

// 电源 CRUD
const openPsuModal = () => {
  editingPsu.value = null
  psuForm.value = {
    wattage: '',
    pn: '',
    part_name: '',
    description: '',
    unit_price: 0,
    applicable_chassis: [],
    note: '',
    sort_order: 0
  }
  psuModalVisible.value = true
}

const editPsu = (item: any) => {
  editingPsu.value = item
  psuForm.value = {
    ...item,
    applicable_chassis: JSON.parse(item.applicable_chassis || '[]')
  }
  psuModalVisible.value = true
}

const savePsu = async () => {
  if (!psuForm.value.wattage || !psuForm.value.part_name) {
    message.warning('请填写必填字段')
    return
  }

  savingPsu.value = true
  try {
    const data = { ...psuForm.value }
    if (editingPsu.value) {
      await axios.put(`/api/l6-chassis/psu/${editingPsu.value.psu_id}`, data)
      message.success('更新成功')
    } else {
      await axios.post('/api/l6-chassis/psu', data)
      message.success('创建成功')
    }
    psuModalVisible.value = false
    loadPsuOptions()
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    savingPsu.value = false
  }
}

const deletePsu = async (psuId: number) => {
  try {
    await axios.delete(`/api/l6-chassis/psu/${psuId}`)
    message.success('删除成功')
    loadPsuOptions()
  } catch (e: any) {
    message.error('删除失败')
  }
}

// 辅助方法
const formatChassisTypes = (chassisJson: string) => {
  try {
    const chassis = JSON.parse(chassisJson || '[]')
    if (chassis.length === 0) return '全部'
    return chassis.join(', ')
  } catch {
    return '全部'
  }
}

const formatDriveBays = (baysJson: string) => {
  try {
    const bays = JSON.parse(baysJson || '[]')
    if (bays.length === 0) return '全部'
    return bays.join(', ')
  } catch {
    return '全部'
  }
}

const formatBackplaneTypes = (backplaneJson: string) => {
  try {
    const backplanes = JSON.parse(backplaneJson || '[]')
    if (backplanes.length === 0) return '全部'
    return backplanes.join(', ')
  } catch {
    return '全部'
  }
}

// 整机价格记录
const priceGroups = ref<any[]>([])
const priceSearchText = ref('')
const showPriceFilter = ref(false)
const expandedPriceModels = ref(new Set<string>())
const matchedPriceIds = ref(new Set<number>())
const loadingPriceRecords = ref(false)

const allPriceRecords = computed(() => {
  return priceGroups.value.flatMap(g => g.records)
})

const isPriceRecordMatched = (record: any) => {
  if (!showPriceFilter.value) return false
  return matchedPriceIds.value.has(record.id)
}

const onPriceFilterChange = (matched: any[], hasFilter: boolean) => {
  matchedPriceIds.value = new Set(hasFilter ? matched.map(r => r.id) : [])
  showPriceFilter.value = true
}

const togglePriceGroup = (model: string) => {
  const newSet = new Set(expandedPriceModels.value)
  if (newSet.has(model)) {
    newSet.delete(model)
  } else {
    newSet.add(model)
  }
  expandedPriceModels.value = newSet
}

const loadPriceRecords = async () => {
  loadingPriceRecords.value = true
  try {
    const res = await axios.get('/api/admin/l6/grouped', {
      params: { search: priceSearchText.value }
    })
    priceGroups.value = res.data.groups || []
  } catch (e: any) {
    message.error('加载价格记录失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loadingPriceRecords.value = false
  }
}

const openPriceRecordModal = () => {
  message.info('新增价格记录功能待实现')
}

const openPriceEditModal = (_record: any) => {
  message.info('编辑价格记录功能待实现')
}

const deletePriceRecord = async (id: number) => {
  try {
    await axios.delete(`/api/admin/l6/${id}`)
    message.success('删除成功')
    loadPriceRecords()
  } catch (e: any) {
    message.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

const formatPrice = (val: any) => {
  if (val == null) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// 初始化
onMounted(() => {
  loadBaseConfigs()
  loadFrontPanelItems()
  loadRearPanelItems()
  loadPsuOptions()
  loadPriceRecords()
})
</script>

<style scoped>
.l6-pricing-page {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 8px;
}

.subtitle {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.main-layout {
  background: transparent;
  min-height: calc(100vh - 160px);
}

.menu-sider {
  border-radius: 8px;
  margin-right: 16px;
}

.menu-sider :deep(.ant-menu) {
  border-right: none;
  padding: 8px 0;
}

.menu-sider :deep(.ant-menu-item) {
  margin: 4px 8px;
  border-radius: 6px;
  font-size: 14px;
}

.main-content {
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 24px;
  min-height: calc(100vh - 160px);
}

.content-panel {
  min-height: 100%;
}

.config-tool-workflow {
  padding: 0;
}

.step-content {
  min-height: 400px;
  margin-bottom: 24px;
}

.step-panel {
  background: var(--el-bg-color-container);
  padding: 24px;
  border-radius: 8px;
}

.step-panel h3 {
  margin-bottom: 16px;
  font-size: 16px;
  font-weight: 500;
}

.step-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.library-panel {
  padding: 16px 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-header h3 {
  font-size: 16px;
  font-weight: 500;
  margin: 0;
}

/* 整机价格记录面板 */
.price-records-panel {
  padding: 16px 0;
}

.price-groups {
  margin-top: 16px;
}

.price-group {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-bg-color-container);
  cursor: pointer;
  transition: background 0.2s;
}

.group-header:hover {
  background: var(--el-bg-color-hover);
}

.group-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.expand-icon {
  transition: transform 0.2s;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.model-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.group-price-range {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.records-wrapper {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease-out;
  background: var(--el-bg-color);
}

.records-wrapper.expanded {
  max-height: 2000px;
  transition: max-height 0.5s ease-in;
}

.records-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  padding: 16px;
}

.filter-wrapper {
  margin-bottom: 16px;
  padding: 16px;
  background: var(--el-bg-color-container);
  border-radius: 8px;
}
</style>
