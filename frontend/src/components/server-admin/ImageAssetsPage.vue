<script setup lang="ts">
/** 图片资产管理 — storage/model-images 池全量文件 + 全库用途画像（机型主图/场景/亮点/详情图库/banner）。
 *  按用途筛选/文件名搜索/页内上传/点图预览/复制链接；「未引用」图可清理（服务端引用兜底防误删）。 */
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import { catalogApi, type ImageAsset } from '@/api/serverConfig'
import { copyText } from '@/utils/clipboard'

/** 用途筛选档（unused=全库引用画像为空，即可清理的死图） */
const KIND_TABS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'unused', label: '未引用' },
  { key: 'main', label: '机型主图' },
  { key: 'gallery', label: '详情图库' },
  { key: 'scenario', label: '场景图' },
  { key: 'highlight', label: '亮点配图' },
  { key: 'banner', label: '门户banner' },
]
const USAGE_LABEL: Record<string, string> = {
  main: '主图', gallery: '详情图库', scenario: '场景图', highlight: '亮点配图', banner: '门户banner',
}

const images = ref<ImageAsset[]>([])
const loading = ref(false)
const uploading = ref(false)
const kw = ref('')
const kind = ref('all')

/** 各档位计数（筛选钮角标） */
const counts = computed(() => {
  const c: Record<string, number> = { all: images.value.length, unused: 0 }
  for (const it of images.value) {
    if (!it.usages.length) c.unused++
    for (const u of it.usages) c[u.kind] = (c[u.kind] || 0) + 1
  }
  return c
})

const filtered = computed(() => {
  const k = kw.value.trim().toLowerCase()
  return images.value.filter(it => {
    if (k && !it.filename.toLowerCase().includes(k)) return false
    if (kind.value === 'unused') return it.usages.length === 0
    if (kind.value !== 'all') return it.usages.some(u => u.kind === kind.value)
    return true
  })
})

async function load() {
  loading.value = true
  try {
    const res = await catalogApi.listImageAssets()
    images.value = res.images
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally { loading.value = false }
}

async function uploadImage(file: File): Promise<boolean> {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { type: 'asset' },
    })
    message.success('已上传')
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  } finally { uploading.value = false }
  return false
}

async function removeAsset(it: ImageAsset) {
  try {
    await catalogApi.deleteImageAsset(it.url)
    message.success('已删除')
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}

const fmtSize = (n: number) => (n >= 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + ' MB' : Math.ceil(n / 1024) + ' KB')
const fmtTime = (ts: number) => new Date(ts * 1000).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })

function copyUrl(url: string) {
  copyText(url, { absolute: true, successMsg: '链接已复制' })
}

/** 用途行展示文案：主图 · 机型A / 场景图 · 机型B；banner 无机型归属只出用途名 */
function usageText(u: ImageAsset['usages'][number]) {
  return USAGE_LABEL[u.kind] + (u.model_name ? ` · ${u.model_name}` : '')
}

onMounted(load)
</script>

<template>
  <div class="img-assets">
    <div class="lib-head">
      <h3>图片资产</h3>
      <span class="hint">本站图片池全量文件与引用画像；机型主图/场景图/详情图库/门户 banner 共用同一内容寻址池（同图去重）</span>
    </div>

    <div class="toolbar">
      <a-input-search v-model:value="kw" class="kw-input" placeholder="按文件名搜索" allowClear />
      <div class="kind-tabs">
        <button
          v-for="t in KIND_TABS"
          :key="t.key"
          type="button"
          class="kind-tab"
          :class="{ active: kind === t.key }"
          @click="kind = t.key"
        >{{ t.label }}<i v-if="counts[t.key]"> {{ counts[t.key] }}</i></button>
      </div>
      <a-upload :show-upload-list="false" :before-upload="uploadImage" accept="image/*" :disabled="uploading">
        <a-button type="primary" :loading="uploading">上传图片</a-button>
      </a-upload>
    </div>

    <a-spin :spinning="loading">
      <div v-if="filtered.length" class="asset-grid">
        <div v-for="it in filtered" :key="it.filename" class="asset-card">
          <a-image class="asset-img" :src="it.url" :alt="it.filename" :preview="true" />
          <div class="asset-meta">
            <div class="asset-name" :title="it.filename">{{ it.filename }}</div>
            <div class="asset-sub">{{ fmtSize(it.size) }} · {{ fmtTime(it.mtime) }}</div>
            <div class="asset-usages">
              <template v-if="it.usages.length">
                <span v-for="(u, i) in it.usages" :key="i" class="usage-chip" :title="usageText(u)">{{ usageText(u) }}</span>
              </template>
              <span v-else class="usage-chip unused">未引用</span>
            </div>
            <div class="asset-ops">
              <button type="button" title="复制链接" @click="copyUrl(it.url)">⧉ 复制链接</button>
              <a-popconfirm
                v-if="!it.usages.length"
                title="删除该图片文件？（无引用，不可恢复）"
                @confirm="removeAsset(it)"
              >
                <button type="button" class="op-del">删除</button>
              </a-popconfirm>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="!loading" class="empty-hint">
        {{ kw || kind !== 'all' ? '没有匹配的图片' : '图片池为空，点右上「上传图片」开始' }}
      </div>
    </a-spin>
  </div>
</template>

<style scoped>
.img-assets { min-height: 300px; }
.lib-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.lib-head h3 { margin: 0; font-size: 17px; font-weight: 700; }
.hint { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted, #6E7582); }

.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.kw-input { width: 240px; }
.kind-tabs { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.kind-tab {
  padding: 5px 12px; font-size: 13px; cursor: pointer;
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-full);
  background: transparent; color: var(--cpq-text-secondary);
  transition: all .15s;
}
.kind-tab:hover { color: var(--cpq-text-primary); border-color: var(--cpq-glass-border-strong); }
.kind-tab.active {
  background: color-mix(in srgb, var(--cpq-accent-primary) 12%, transparent);
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-text-primary); font-weight: 600;
}
.kind-tab i { font-style: normal; font-size: var(--cpq-font-size-xs); opacity: .65; }

.asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.asset-card {
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-md);
  overflow: hidden; background: var(--cpq-bg-card);
  display: flex; flex-direction: column;
}
.asset-img :deep(img) { width: 100%; height: 130px; object-fit: cover; display: block; }
.asset-meta { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
.asset-name {
  font-size: 13px; font-weight: 600; color: var(--cpq-text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.asset-sub { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted, #6E7582); }
.asset-usages { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; align-content: flex-start; }
.usage-chip {
  font-size: 11px; padding: 1px 8px; border-radius: var(--cpq-radius-full);
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  background: var(--cpq-overlay-w8); color: var(--cpq-text-secondary);
  border: 1px solid var(--cpq-glass-border);
}
.usage-chip.unused { color: var(--cpq-color-warning); border-color: var(--cpq-warn-border); background: var(--cpq-warn-surface); }

.asset-ops { display: flex; gap: 8px; margin-top: 2px; }
.asset-ops button {
  padding: 3px 10px; font-size: var(--cpq-font-size-xs); cursor: pointer;
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-sm);
  background: transparent; color: var(--cpq-text-secondary);
  transition: all .15s;
}
.asset-ops button:hover { color: var(--cpq-text-primary); border-color: var(--cpq-glass-border-strong); }
.asset-ops .op-del:hover { color: var(--cpq-accent-danger); border-color: var(--cpq-accent-danger); }

.empty-hint { padding: 60px 0; text-align: center; color: var(--cpq-text-muted, #6E7582); font-size: 13.5px; }
</style>
