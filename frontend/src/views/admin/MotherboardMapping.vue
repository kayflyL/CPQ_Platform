<template>
  <div class="motherboard-mapping">
    <!-- 说明卡片 -->
    <a-card class="info-card" :bordered="false">
      <div class="info-content">
        <span class="info-icon">💡</span>
        <div>
          <div class="info-title">主板映射规则</div>
          <div class="info-desc">
            当报价单包含CPU时，系统通过此规则确定使用哪款主板，用于L6整机成本计算。
            将下方的CPU型号拖到对应的主板上即可完成映射。
          </div>
        </div>
      </div>
    </a-card>

    <!-- 主板区域 -->
    <div class="motherboards-area">
      <div
        v-for="mb in motherboards"
        :key="mb.name"
        class="motherboard-zone"
        :class="{ 'drag-over': dragOverMb === mb.name }"
        @dragover.prevent="onDragOverMb(mb.name)"
        @dragleave="dragOverMb = ''"
        @drop="onDropToMb(mb.name, $event)"
      >
        <!-- SVG 主板示意图 -->
        <div class="mb-visual">
          <svg viewBox="0 0 280 200" class="mb-svg">
            <!-- PCB 底板 -->
            <rect x="5" y="5" width="270" height="190" rx="8" ry="8"
                  :fill="mb.color" stroke="#555" stroke-width="2" />
            <!-- PCB 纹理线条 -->
            <line x1="20" y1="50" x2="260" y2="50" stroke="#3a5a3a" stroke-width="0.5" opacity="0.5" />
            <line x1="20" y1="100" x2="260" y2="100" stroke="#3a5a3a" stroke-width="0.5" opacity="0.5" />
            <line x1="20" y1="150" x2="260" y2="150" stroke="#3a5a3a" stroke-width="0.5" opacity="0.5" />
            <!-- CPU Socket 1 -->
            <rect x="40" y="30" width="80" height="60" rx="4" ry="4"
                  fill="#1a1a2e" stroke="#888" stroke-width="1.5" />
            <rect x="48" y="38" width="64" height="44" rx="2" ry="2"
                  fill="#0d0d1a" stroke="#666" stroke-width="1" />
            <text x="80" y="65" text-anchor="middle" fill="#aaa" font-size="10">CPU 1</text>
            <!-- CPU Socket 2 -->
            <rect x="160" y="30" width="80" height="60" rx="4" ry="4"
                  fill="#1a1a2e" stroke="#888" stroke-width="1.5" />
            <rect x="168" y="38" width="64" height="44" rx="2" ry="2"
                  fill="#0d0d1a" stroke="#666" stroke-width="1" />
            <text x="200" y="65" text-anchor="middle" fill="#aaa" font-size="10">CPU 2</text>
            <!-- 内存插槽 -->
            <g v-for="i in 8" :key="'mem'+i">
              <rect :x="30 + (i-1) * 28" y="110" width="20" height="8" rx="1"
                    fill="#2d4a2d" stroke="#5a5" stroke-width="0.5" />
            </g>
            <!-- 主板名称 -->
            <text x="140" y="175" text-anchor="middle" fill="#ccc" font-size="14" font-weight="bold">
              {{ mb.name }}
            </text>
          </svg>
        </div>

        <!-- 已映射CPU列表 -->
        <div class="mapped-cpus">
          <div class="mapped-header">
            已映射 ({{ mappedCpus[mb.name]?.length || 0 }})
          </div>
          <draggable
            :list="mappedCpus[mb.name]"
            :group="{ name: 'cpus', pull: true, put: true }"
            item-key="cpu"
            class="mapped-list"
            ghost-class="ghost"
            @change="onMappedChange(mb.name)"
          >
            <template #item="{ element }">
              <div class="cpu-tag mapped">
                <span>{{ element }}</span>
                <a-button type="text" size="small" class="remove-btn" @click="unmapCpu(element, mb.name)">×</a-button>
              </div>
            </template>
            <template #footer>
              <div v-if="!mappedCpus[mb.name]?.length" class="empty-hint">
                拖拽CPU到此处
              </div>
            </template>
          </draggable>
        </div>
      </div>
    </div>

    <!-- CPU池 -->
    <a-card class="cpu-pool-card" :bordered="false">
      <template #title>
        <span>📦 未映射CPU池</span>
        <a-tag color="orange" style="margin-left: 12px">{{ unmappedCpus.length }} 个待映射</a-tag>
      </template>
      <draggable
        :list="unmappedCpus"
        :group="{ name: 'cpus', pull: true, put: true }"
        item-key="cpu"
        class="cpu-pool"
        ghost-class="ghost"
        @change="onPoolChange"
      >
        <template #item="{ element }">
          <div class="cpu-tag pool">{{ element }}</div>
        </template>
        <template #footer>
          <div v-if="!unmappedCpus.length" class="empty-hint">
            所有CPU都已映射 ✅
          </div>
        </template>
      </draggable>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import draggable from 'vuedraggable'

const API_BASE = '/api/rules'

interface MbConfig {
  name: string
  color: string
}

const motherboards: MbConfig[] = [
  { name: 'Polaris MB', color: '#1a3a2a' },
  { name: 'Orion MB', color: '#1a2a3a' },
]

const allCpus = ref<string[]>([])
const mappedCpus = ref<Record<string, string[]>>({
  'Polaris MB': [],
  'Orion MB': [],
})
const unmappedCpus = ref<string[]>([])
const saving = ref(false)
const dragOverMb = ref('')

// 加载数据
const loadData = async () => {
  try {
    const [cpuResp, mapResp] = await Promise.all([
      axios.get(`${API_BASE}/cpu-list`),
      axios.get(`${API_BASE}/motherboard-mappings`),
    ])

    allCpus.value = cpuResp.data.cpus || []
    const mappings = mapResp.data.mappings || []

    // 初始化映射
    const polaris: string[] = []
    const orion: string[] = []
    const mappedSet = new Set<string>()

    for (const m of mappings) {
      const cpu = m.cpu_feature
      const mb = m.motherboard_model
      if (mb === 'Polaris MB') {
        polaris.push(cpu)
        mappedSet.add(cpu)
      } else if (mb === 'Orion MB') {
        orion.push(cpu)
        mappedSet.add(cpu)
      }
    }

    mappedCpus.value = {
      'Polaris MB': polaris,
      'Orion MB': orion,
    }

    // 未映射的CPU
    unmappedCpus.value = allCpus.value.filter(c => !mappedSet.has(c))
  } catch (e: any) {
    message.error('加载数据失败: ' + (e.message || ''))
  }
}

// 拖拽到主板
const onDragOverMb = (mbName: string) => {
  dragOverMb.value = mbName
}

const onDropToMb = (_mbName: string, _event: DragEvent) => {
  dragOverMb.value = ''
  // vuedraggable handles this via group
}

// 映射变化后同步
const onMappedChange = (mbName: string) => {
  // 确保CPU不在其他主板和池子里
  for (const otherMb of motherboards) {
    if (otherMb.name !== mbName) {
      mappedCpus.value[otherMb.name] = mappedCpus.value[otherMb.name].filter(
        c => !mappedCpus.value[mbName].includes(c)
      )
    }
  }
  unmappedCpus.value = unmappedCpus.value.filter(
    c => !mappedCpus.value[mbName].includes(c)
  )
}

const onPoolChange = () => {
  // CPU从池子移出时，确保不在任何主板映射中重复
  for (const mb of motherboards) {
    mappedCpus.value[mb.name] = mappedCpus.value[mb.name].filter(
      c => !unmappedCpus.value.includes(c)
    )
  }
}

// 取消映射
const unmapCpu = (cpu: string, mbName: string) => {
  mappedCpus.value[mbName] = mappedCpus.value[mbName].filter(c => c !== cpu)
  if (!unmappedCpus.value.includes(cpu)) {
    unmappedCpus.value.push(cpu)
  }
}

// 保存（暴露给父组件）
const saveMappings = async () => {
  saving.value = true
  try {
    const payload: any[] = []
    for (const mb of motherboards) {
      for (const cpu of mappedCpus.value[mb.name]) {
        payload.push({
          cpu_feature: cpu,
          motherboard_model: mb.name,
          priority: 1,
        })
      }
    }
    await axios.put(`${API_BASE}/motherboard-mappings`, payload)
  } catch (e: any) {
    throw e
  } finally {
    saving.value = false
  }
}

// 重置（暴露给父组件）
const resetMappings = () => {
  loadData()
}

// 暴露方法给父组件
defineExpose({
  saveMappings,
  resetMappings,
  loadData,
})

onMounted(loadData)
</script>

<style scoped>
.motherboard-mapping {
  padding: 0;
}

/* 说明卡片 */
.info-card {
  background: var(--cpq-bg-secondary);
  margin-bottom: 16px;
}
.info-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.info-icon {
  font-size: 24px;
  line-height: 1;
}
.info-title {
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 4px;
}
.info-desc {
  color: var(--cpq-text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

/* 主板区域 */
.motherboards-area {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.motherboard-zone {
  flex: 1;
  background: var(--cpq-bg-secondary);
  border: 2px solid var(--cpq-border-secondary);
  border-radius: 8px;
  padding: 16px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.motherboard-zone.drag-over {
  border-color: var(--cpq-accent-primary);
  box-shadow: 0 0 12px var(--cpq-overlay-info20);
}

/* SVG主板图 */
.mb-visual {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}
.mb-svg {
  width: 100%;
  max-width: 280px;
  height: auto;
}

/* 已映射列表 */
.mapped-header {
  color: var(--cpq-text-secondary);
  font-size: 12px;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--cpq-border-secondary);
}
.mapped-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 40px;
  padding: 4px;
}

/* CPU标签 */
.cpu-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: grab;
  transition: transform 0.15s, box-shadow 0.15s;
  user-select: none;
}
.cpu-tag:active {
  cursor: grabbing;
}
.cpu-tag.pool {
  background: var(--cpq-bg-tertiary);
  color: var(--cpq-text-primary);
  border: 1px solid var(--cpq-border-secondary);
}
.cpu-tag.pool:hover {
  background: var(--cpq-border-light);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}
.cpu-tag.mapped {
  background: var(--cpq-overlay-a10);
  color: var(--cpq-accent-success);
  border: 1px solid var(--cpq-overlay-a30);
}
.remove-btn {
  color: var(--cpq-accent-danger) !important;
  font-size: 14px;
  padding: 0 2px !important;
  margin-left: 2px;
  line-height: 1 !important;
  height: auto !important;
}

/* 拖拽幽灵 */
.ghost {
  opacity: 0.4;
  background: var(--cpq-accent-primary) !important;
}

/* CPU池 */
.cpu-pool-card {
  background: var(--cpq-bg-secondary);
  margin-bottom: 16px;
}
.cpu-pool-card :deep(.ant-card-head) {
  border-bottom-color: var(--cpq-border-secondary);
}
.cpu-pool-card :deep(.ant-card-head-title) {
  color: var(--cpq-text-primary);
  display: flex;
  align-items: center;
}
.cpu-pool {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 60px;
  padding: 8px 0;
}

/* 空提示 */
.empty-hint {
  color: var(--text-tertiary);
  font-size: 12px;
  padding: 8px;
  font-style: italic;
}

/* 响应式 */
@media (max-width: 768px) {
  .motherboards-area {
    flex-direction: column;
  }
}
</style>
