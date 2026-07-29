<template>
  <!-- 解析规则编辑器：左栏整体（区域定义 + 字段映射 + KP 分类映射 + 两个编辑 modal）。
       内部走 useExcelParser() 单例，与设置页/商机弹窗共享同一份规则与预览状态。
       改完任意规则 → saveRegion/saveFieldRule 内部已自动 loadRules + refreshPreview 重算。 -->
  <div class="parse-rules-editor">
    <a-card title="解析规则" size="small">
      <template #extra>
        <a-button size="small" @click="showAddRegionModal = true">+ 区域</a-button>
      </template>

      <!-- 区域定义 -->
      <div class="rule-section">
        <h4>区域定义</h4>
        <a-collapse v-model:activeKey="expandedRegions" :bordered="false">
          <a-collapse-panel v-for="region in parseRegions" :key="region.id" :header="region.name">
            <template #extra>
              <a-space>
                <a-button size="small" @click.stop="editRegion(region)">编辑</a-button>
                <a-popconfirm title="确定删除？" @confirm="deleteRegion(region.id)">
                  <a-button size="small" danger>删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
            <a-descriptions :column="1" size="small">
              <a-descriptions-item label="起始关键词">{{ region.start_keywords || '—' }}</a-descriptions-item>
              <a-descriptions-item label="结束关键词">{{ region.end_keywords || '—' }}</a-descriptions-item>
              <a-descriptions-item label="跳过行数">{{ region.skip_header_rows }}</a-descriptions-item>
            </a-descriptions>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 字段映射 -->
      <div class="rule-section">
        <h4>字段映射</h4>
        <a-button size="small" @click="showAddFieldRuleModal = true" style="margin-bottom: 8px;">
          + 字段规则
        </a-button>
        <a-table
          :dataSource="parseFieldRules"
          :columns="fieldRuleColumns"
          :pagination="false"
          size="small"
          rowKey="id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'enabled'">
              <a-tag :color="record.enabled ? 'green' : 'default'" size="small">
                {{ record.enabled ? '✓' : '✗' }}
              </a-tag>
            </template>
            <template v-if="column.key === 'action'">
              <a-space :size="2">
                <a-button type="link" size="small" @click="editFieldRule(record)">
                  <template #icon><EditOutlined /></template>
                </a-button>
                <a-popconfirm title="确定删除？" @confirm="deleteFieldRule(record.id)">
                  <a-button type="link" size="small" danger>
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>
    </a-card>

    <!-- KP 分类映射 -->
    <a-card title="KP 分类映射" size="small" style="margin-top: 12px;">
      <div class="kp-mapping-add">
        <a-input
          v-model:value="newKeyword"
          placeholder="关键词（如 CPU、Memory）"
          style="width: 100px"
          size="small"
        />
        <a-select
          v-model:value="newCategory"
          placeholder="分类"
          style="width: 90px"
          size="small"
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
        <a-button type="primary" size="small" :loading="adding" @click="handleAddMapping">
          +
        </a-button>
      </div>

      <a-table
        :columns="mappingColumns"
        :data-source="kpMappings"
        :pagination="false"
        row-key="id"
        size="small"
        :loading="loadingMappings"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'keyword'">
            <a-input
              v-if="editingMappingId === record.id"
              v-model:value="record.keyword"
              size="small"
            />
            <span v-else>{{ record.keyword }}</span>
          </template>
          <template v-if="column.key === 'category'">
            <a-select
              v-if="editingMappingId === record.id"
              v-model:value="record.category"
              size="small"
              style="width: 90px"
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
            <span v-else>{{ record.category }}</span>
          </template>
          <template v-if="column.key === 'action'">
            <a-space :size="2">
              <a-button
                v-if="editingMappingId === record.id"
                type="link"
                size="small"
                @click="handleSaveMappingEdit(record)"
              >
                ✓
              </a-button>
              <a-button
                v-if="editingMappingId === record.id"
                type="link"
                size="small"
                @click="handleCancelMappingEdit"
              >
                ✗
              </a-button>
              <a-button
                v-if="editingMappingId !== record.id"
                type="link"
                size="small"
                @click="handleEditMapping(record)"
              >
                <template #icon><EditOutlined /></template>
              </a-button>
              <a-popconfirm
                title="确定删除此映射？"
                @confirm="handleDeleteMapping(record.id)"
              >
                <a-button type="link" size="small" danger>
                  <template #icon><DeleteOutlined /></template>
                </a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 添加/编辑区域弹窗 -->
    <a-modal
      v-model:open="showAddRegionModal"
      :title="editingRegion ? '编辑区域' : '添加区域'"
      @ok="saveRegion"
      @cancel="cancelEditRegion"
    >
      <a-form :model="regionForm" layout="vertical">
        <a-form-item label="区域名称" required>
          <a-input v-model:value="regionForm.name" placeholder="如: header, L6, KP, Warranty" />
        </a-form-item>
        <a-form-item label="起始关键词">
          <a-select
            v-model:value="regionForm.startKeywordsList"
            mode="tags"
            :token-separators="[',']"
            placeholder="输入关键词后按回车添加"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="结束关键词">
          <a-select
            v-model:value="regionForm.endKeywordsList"
            mode="tags"
            :token-separators="[',']"
            placeholder="输入关键词后按回车添加"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="跳过行数">
          <a-input-number v-model:value="regionForm.skip_header_rows" :min="0" style="width: 100%;" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="regionForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 添加/编辑字段规则弹窗 -->
    <a-modal
      v-model:open="showAddFieldRuleModal"
      :title="editingFieldRule ? '编辑字段规则' : '添加字段规则'"
      @ok="saveFieldRule"
      @cancel="cancelEditFieldRule"
      width="600px"
    >
      <a-form :model="fieldRuleForm" layout="vertical">
        <a-form-item label="字段" required>
          <a-select v-model:value="fieldRuleForm.field_key" placeholder="选择字段" show-search :filter-option="filterOption">
            <a-select-option v-for="field in businessFields" :key="field.key" :value="field.key" :label="field.label">
              {{ field.label }} ({{ field.key }})
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="所属区域" required>
          <a-select v-model:value="fieldRuleForm.region" placeholder="选择区域">
            <a-select-option v-for="region in parseRegions" :key="region.name" :value="region.name">
              {{ region.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="提取方式" required>
          <a-radio-group v-model:value="fieldRuleForm.source_type">
            <a-radio value="keyword">关键词匹配</a-radio>
            <a-radio value="column">列提取</a-radio>
          </a-radio-group>
        </a-form-item>

        <!-- 关键词匹配配置 -->
        <template v-if="fieldRuleForm.source_type === 'keyword'">
          <a-form-item label="关键词列表" required>
            <a-select
              v-model:value="fieldRuleForm.source_config.keywords"
              mode="tags"
              placeholder="输入关键词后按回车"
              style="width: 100%;"
            />
          </a-form-item>
          <a-form-item label="值偏移量">
            <a-input-number
              v-model:value="fieldRuleForm.source_config.value_offset"
              :min="1"
              style="width: 100%;"
              placeholder="关键词右侧第几列取值"
            />
          </a-form-item>
        </template>

        <!-- 列提取配置 -->
        <template v-if="fieldRuleForm.source_type === 'column'">
          <a-form-item label="列字母">
            <a-input
              v-model:value="fieldRuleForm.source_config.col"
              placeholder="如: A, B, C, D（表头标签未命中时的回落列）"
              style="width: 100%;"
            />
          </a-form-item>
          <a-form-item label="表头标签（自适应列定位）">
            <a-select
              v-model:value="fieldRuleForm.source_config.header_labels"
              mode="tags"
              :token-separators="[',']"
              placeholder="如 catalogue、类别。配了则优先按表头标签定位列，兼容不同模板的列偏移"
              style="width: 100%;"
            />
          </a-form-item>
        </template>

        <a-form-item label="启用">
          <a-switch v-model:checked="fieldRuleForm.enabled" />
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="fieldRuleForm.sort_order" :min="0" style="width: 100%;" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { useExcelParser } from '@/composables/useExcelParser'

const {
  // 列表数据
  parseRegions, parseFieldRules, businessFields, kpMappings, loadingMappings,
  fieldRuleColumns, mappingColumns,
  // KP 映射
  newKeyword, newCategory, adding, editingMappingId,
  handleAddMapping, handleEditMapping, handleCancelMappingEdit,
  handleSaveMappingEdit, handleDeleteMapping,
  // 区域 CRUD
  expandedRegions, showAddRegionModal, editingRegion, regionForm,
  editRegion, cancelEditRegion, saveRegion, deleteRegion,
  // 字段规则 CRUD
  showAddFieldRuleModal, editingFieldRule, fieldRuleForm,
  editFieldRule, cancelEditFieldRule, saveFieldRule, deleteFieldRule,
  // 辅助
  filterOption
} = useExcelParser()
</script>

<style scoped>
.parse-rules-editor {
  display: flex;
  flex-direction: column;
}

.rule-section {
  margin-bottom: 16px;
}

.rule-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-light);
}

.kp-mapping-add {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
</style>
