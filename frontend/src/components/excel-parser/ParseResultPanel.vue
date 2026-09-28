<template>
  <!-- 解析结果面板（共享）：设置页右栏与商机上传弹窗右栏复用同一套展示。
       静态字段 + 动态区域均带溯源（行/列/关键词）；解析追踪时间线只归设置页，不在此。 -->
  <div class="parse-result-panel">
    <template v-if="parseResult">
      <!-- 静态字段 -->
      <div v-if="staticFields.length" class="result-section">
        <h4>静态字段</h4>
        <a-descriptions :column="1" size="small" bordered>
          <a-descriptions-item
            v-for="[key, field] in staticFields"
            :key="key"
            :label="String(key)"
          >
            <div>{{ (field as any).value }}</div>
            <div v-if="(field as any).source" class="source-info">
              <a-tag size="small">行 {{ (field as any).source.row + 1 }}</a-tag>
              <a-tag size="small">列 {{ (field as any).source.col_letter || (field as any).source.col + 1 }}</a-tag>
              <span v-if="(field as any).source.keyword" class="keyword-tag">
                关键词: {{ (field as any).source.keyword }}
              </span>
            </div>
          </a-descriptions-item>
        </a-descriptions>
      </div>

      <!-- 动态区域 -->
      <div v-if="regionEntries.length" class="result-section">
        <h4>动态区域</h4>
        <a-collapse v-model:activeKey="expanded" :bordered="false">
          <a-collapse-panel
            v-for="[regionKey, items] in regionEntries"
            :key="regionKey"
            :header="`${regionLabel(regionKey)} (${(items as any[]).length} 行)`"
          >
            <a-table
              :dataSource="(items as any[]).map((item: Record<string, any>, idx: number) => ({ ...item, _key: idx }))"
              :columns="getDynamicColumns(items as any[])"
              :pagination="false"
              size="small"
              rowKey="_key"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === '_trace'">
                  <a-tooltip>
                    <template #title>
                      <div v-for="trace in record._trace" :key="trace.field_key">
                        {{ trace.field_key }}: 行 {{ trace.source.row + 1 }}, 列 {{ trace.source.col_letter || trace.source.col + 1 }}
                      </div>
                    </template>
                    <a-tag color="blue">溯源</a-tag>
                  </a-tooltip>
                </template>
              </template>
            </a-table>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <a-empty
        v-if="!staticFields.length && !regionEntries.length"
        description="暂无解析结果"
        :image-style="{ height: '40px' }"
      />
    </template>
    <a-empty v-else description="暂无解析结果" :image-style="{ height: '40px' }" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useExcelParser } from '@/composables/useExcelParser'

const props = defineProps<{ parseResult: any }>()

const { parseRegions, getDynamicColumns } = useExcelParser()

const expanded = ref<string[]>([])

const staticFields = computed(() =>
  Object.entries(props.parseResult?.static_fields || {}).filter(([, f]) => (f as any)?.value))

const regionEntries = computed(() =>
  Object.entries(props.parseResult?.dynamic_regions || {}).filter(([, v]) => Array.isArray(v) && v.length))

// 新解析结果到达时自动展开全部区域（与设置页既有行为一致）
watch(() => props.parseResult?.dynamic_regions, (dr) => {
  expanded.value = dr ? Object.keys(dr) : []
}, { immediate: true })

function regionLabel(regionKey: string): string {
  const region = parseRegions.value.find((r: any) =>
    (r.region_key || '').toLowerCase() === regionKey.toLowerCase() || r.name === regionKey)
  return region?.name || regionKey.toUpperCase()
}
</script>

<style scoped>
.result-section {
  margin-bottom: 16px;
}

.result-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-light);
}

.source-info {
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.keyword-tag {
  margin-left: 8px;
  color: var(--cpq-color-primary);
}
</style>
