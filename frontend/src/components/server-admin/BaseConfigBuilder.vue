<script setup lang="ts">
/** 基准配置列表（管理面）— 新建/编辑跳全页编辑器 /servers/base-configs/:id。 */
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { baseConfigApi, type BaseConfig } from '@/api/serverConfig'

const router = useRouter()
const route = useRoute()
const configs = ref<BaseConfig[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try { configs.value = (await baseConfigApi.list()).configs } finally { loading.value = false }
}
function openNew() { router.push('/servers/base-configs/new') }
function openEdit(b: any) { router.push(`/servers/base-configs/${b.id}`) }
async function remove(id: number, name: string) {
  await baseConfigApi.delete(id); message.success('已删除 ' + name); load()
}
const columns = [
  { title: '基准名称', dataIndex: 'name', key: 'name' },
  { title: '系列', dataIndex: 'series', key: 'series', width: 90 },
  { title: '形态', dataIndex: 'form', key: 'form', width: 70 },
  { title: '盘位', dataIndex: 'bays', key: 'bays', width: 70 },
  { title: '料件数', dataIndex: 'parts_count', key: 'parts_count', width: 80 },
  { title: '合计', dataIndex: 'total_price', key: 'total_price', width: 110 },
  { title: '操作', key: 'op', width: 120 },
]
watch(() => route.query.refresh, (v) => { if (v === 'base-config') load() })
onMounted(load)
</script>

<template>
  <div class="panel glass">
    <div class="lib-head">
      <h3>基准配置</h3>
      <a-button type="primary" size="small" @click="openNew">+ 新建基准配置（挑件组装）</a-button>
    </div>
    <a-table :data-source="configs" :columns="columns" :loading="loading" row-key="id" size="small" :pagination="false">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'parts_count'"><span class="cell-num">{{ record.parts_count ?? 0 }}</span></template>
        <template v-else-if="column.key === 'total_price'"><span class="cell-price">¥{{ (record.total_price ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span></template>
        <template v-else-if="column.key === 'op'">
          <a-button size="small" link @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="删除该基准配置？" @confirm="remove(record.id, record.name)">
            <a-button size="small" link danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.cell-num { font-variant-numeric: tabular-nums; color: var(--cpq-text-secondary, #9BA1AA); }
.cell-price { font-weight: 700; color: var(--cpq-accent-primary); font-variant-numeric: tabular-nums; }
</style>
