<script setup lang="ts">
/**
 * 选型配置自定义节点组件
 * 使用 @antv/x6-vue-shape 渲染带图标、品类色、hover 效果的节点
 */
import { computed } from 'vue'
import {
  ApiOutlined,
  DatabaseOutlined,
  FireOutlined,
  ThunderboltOutlined,
  HddOutlined,
  PartitionOutlined,
  UsbOutlined,
  ControlOutlined,
  PoweroffOutlined,
  SyncOutlined,
  WifiOutlined,
  AppstoreOutlined,
} from '@ant-design/icons-vue'
import { getCategoryStyle } from './selectionConfig'

const props = defineProps<{
  node?: {
    getData: () => { label: string }
    setData: (data: any) => void
  }
}>()

// 从节点获取标签
const label = computed(() => props.node?.getData()?.label || '')

// 品类样式
const style = computed(() => getCategoryStyle(label.value))

// 图标映射
const ICON_MAP: Record<string, any> = {
  CPU: ApiOutlined,
  Memory: DatabaseOutlined,
  GPU: FireOutlined,
  'GPU电源线': ThunderboltOutlined,
  '硬盘': HddOutlined,
  '背板': PartitionOutlined,
  HBA: UsbOutlined,
  RAID: ControlOutlined,
  PSU: PoweroffOutlined,
  '风扇': SyncOutlined,
  '网卡': WifiOutlined,
}

const IconComponent = computed(() => ICON_MAP[label.value] || AppstoreOutlined)
</script>

<template>
  <div
    class="selection-node"
    :style="{
      '--node-bg': style.bg,
      '--node-border': style.border,
      '--node-text': style.text,
    }"
  >
    <div class="node-icon">
      <component :is="IconComponent" />
    </div>
    <span class="node-label">{{ label }}</span>
  </div>
</template>

<style scoped>
.selection-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--node-bg);
  border: 1.5px solid var(--node-border);
  border-radius: 10px;
  min-width: 120px;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}

.selection-node:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.node-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--node-border);
  font-size: 16px;
}

.node-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--node-text);
  white-space: nowrap;
}
</style>