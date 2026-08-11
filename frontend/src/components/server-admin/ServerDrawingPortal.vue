<script setup lang="ts">
/**
 * 服务器图纸配置（卡片入口，嵌于服务器管理「图纸配置」tab）。
 * 卡片网格展示各机型图纸预览：有图显示 SVG 缩略图，无图显示占位；点卡进入对应机型的图纸编辑器。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { catalogApi, type ServerModel } from '@/api/serverConfig'

const router = useRouter()
const models = ref<ServerModel[]>([])
const loading = ref(false)
const filter = ref<'all' | 'uploaded' | 'empty'>('all')

const hasDrawing = (m: ServerModel) => !!m.drawing?.svg_url

const counts = computed(() => ({
  all: models.value.length,
  uploaded: models.value.filter(hasDrawing).length,
  empty: models.value.filter(m => !hasDrawing(m)).length,
}))

const filtered = computed(() => {
  if (filter.value === 'uploaded') return models.value.filter(hasDrawing)
  if (filter.value === 'empty') return models.value.filter(m => !hasDrawing(m))
  return models.value
})

async function load() {
  loading.value = true
  try {
    const res = await catalogApi.listModels()
    models.value = res.models || []
  } catch {
    models.value = []
  } finally {
    loading.value = false
  }
}

function enter(m: ServerModel) {
  if (!m.id) return
  router.push('/servers/drawing/' + m.id)
}

onMounted(load)
</script>

<template>
  <div class="sdp">
    <div class="sdp-head">
      <p class="sdp-tip">上传机型 SVG 图纸并圈出区域（盘位 / CPU·内存 / 风扇 / 电源 / IO…），选型配置页点击区域可查看相关规则。点卡片进入对应机型的图纸编辑器。</p>
      <a-radio-group v-model:value="filter" size="small" button-style="solid">
        <a-radio-button value="all">全部 {{ counts.all }}</a-radio-button>
        <a-radio-button value="uploaded">已上传 {{ counts.uploaded }}</a-radio-button>
        <a-radio-button value="empty">未上传 {{ counts.empty }}</a-radio-button>
      </a-radio-group>
    </div>

    <a-spin :spinning="loading">
      <div v-if="filtered.length" class="sdp-grid">
        <div v-for="m in filtered" :key="m.id" class="sdp-card is-clickable" @click="enter(m)">
          <div class="sdp-thumb">
            <img v-if="m.drawing?.svg_url" :src="m.drawing.svg_url" :alt="m.name" />
            <span v-else class="sdp-thumb-ph">SVG</span>
            <span class="sdp-status" :class="m.drawing?.svg_url ? 'ok' : 'no'">
              {{ m.drawing?.svg_url ? '已上传图纸' : '未上传' }}
            </span>
          </div>
          <div class="sdp-name">{{ m.name }}</div>
          <div class="sdp-specs">
            <span><i>形态</i>{{ m.base_config?.form || '—' }}</span>
            <span><i>盘位</i>{{ m.base_config?.bays ?? '—' }}</span>
            <span><i>系列</i>{{ m.base_config?.series || '—' }}</span>
          </div>
        </div>
      </div>
      <a-empty v-else-if="!loading" description="暂无机型" />
    </a-spin>
  </div>
</template>

<style scoped>
.sdp { display: flex; flex-direction: column; gap: 12px; }
.sdp-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 10px; }
.sdp-tip { margin: 0; color: var(--cpq-text-muted); font-size: 12.5px; line-height: 1.6; max-width: 720px; }
.sdp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(248px, 1fr)); gap: 16px; }
.sdp-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.sdp-card.is-clickable { cursor: pointer; }
.sdp-card.is-clickable:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-2px);
  box-shadow: var(--cpq-glass-card-shadow-hover);
}
.sdp-thumb {
  position: relative;
  height: 148px;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.22);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--cpq-glass-border);
}
.sdp-thumb img { width: 100%; height: 100%; object-fit: contain; display: block; }
.sdp-thumb-ph {
  color: var(--cpq-text-disabled);
  font-size: 13px;
  letter-spacing: 2px;
  border: 1px dashed var(--cpq-overlay-w20, rgba(255, 255, 255, 0.2));
  border-radius: 8px;
  padding: 6px 14px;
}
.sdp-status {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 11px;
  line-height: 1;
  padding: 4px 8px;
  border-radius: 8px;
  color: #fff;
  backdrop-filter: blur(4px);
}
.sdp-status.ok { background: rgba(82, 201, 160, 0.85); }
.sdp-status.no { background: rgba(255, 255, 255, 0.22); }
.sdp-name { font-size: 15px; font-weight: 700; color: var(--cpq-text-primary); }
.sdp-specs { display: flex; gap: 10px; flex-wrap: wrap; }
.sdp-specs span { font-size: 12px; color: var(--cpq-text-secondary); }
.sdp-specs i { font-style: normal; color: var(--cpq-text-muted); margin-right: 3px; }
</style>
