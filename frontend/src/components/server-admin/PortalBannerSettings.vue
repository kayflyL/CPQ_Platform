<script setup lang="ts">
/** 门户设置 — 服务器门户 banner 标题 + 轮播图管理（system_config.server_portal_banner）。
 *  标题留空=门户回落内置默认；每张轮播图可配独立副标题（缩略图下输入框，门户随图切换展示，留空不显示）。
 *  图片复用 /models/image?type=portal-banner 上传，按顺序轮播（首张=主图），缩略图行内排序/删除。 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import { catalogApi, type PortalBannerImage } from '@/api/serverConfig'

const DEFAULTS = {
  title: '配置一台服务器',
}

const title = ref('')
const images = ref<PortalBannerImage[]>([])
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)

async function load() {
  loading.value = true
  try {
    const cfg = await catalogApi.getPortalBanner()
    title.value = cfg.title || ''
    images.value = (cfg.images || []).map(e => ({ url: e.url, subtitle: e.subtitle || '' }))
  } catch (e: any) {
    message.error(e.response?.data?.detail || '加载失败')
  } finally { loading.value = false }
}

async function uploadImage(file: File): Promise<boolean> {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { type: 'portal-banner' },
    })
    images.value.push({ url: resp.data.url })
    message.success('已上传，保存后生效')
    loadLibrary()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  } finally { uploading.value = false }
  return false
}

// ---- 本站图片库（storage/model-images/ 全量文件递归，含机型主图/场景图，点图即复用） ----
const libImages = ref<{ url: string; filename: string }[]>([])
async function loadLibrary() {
  try {
    const res = await axios.get('/api/server-catalog/portal-banner/images')
    libImages.value = res.data.images || []
  } catch { /* 图库加载失败不阻塞编辑 */ }
}

/** 复制图片链接（站内相对路径补全为绝对 URL，站外也能直接用） */
async function copyUrl(url: string) {
  const full = /^https?:/.test(url) ? url : location.origin + url
  try {
    await navigator.clipboard.writeText(full)
    message.success('链接已复制')
  } catch {
    const ta = document.createElement('textarea')
    ta.value = full
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    message.success('链接已复制')
  }
}

// ---- 按链接添加（粘贴本站 /api/... 或外部 http 图直链） ----
const addUrl = ref('')
function addByUrl() {
  const u = addUrl.value.trim()
  if (!u) return
  appendImage(u)
  addUrl.value = ''
}

function appendImage(url: string) {
  if (images.value.some(e => e.url === url)) {
    message.warning('该图片已在列表中')
    return
  }
  images.value.push({ url })
  message.success('已加入列表，保存后生效')
}

function removeImage(i: number) { images.value.splice(i, 1) }
function moveImage(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= images.value.length) return
  const [item] = images.value.splice(i, 1)
  images.value.splice(j, 0, item)
}

async function save() {
  saving.value = true
  try {
    await catalogApi.savePortalBanner({
      title: title.value.trim(),
      images: images.value.map(e => ({ url: e.url, subtitle: (e.subtitle || '').trim() })),
    })
    message.success('已保存，刷新门户生效')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

onMounted(() => {
  load()
  loadLibrary()
})
</script>

<template>
  <div class="panel glass">
    <div class="lib-head">
      <h3>门户设置</h3>
      <span class="hint">服务器页（/servers）banner 的文案与轮播图</span>
    </div>

    <a-spin :spinning="loading">
      <a-form layout="vertical" class="banner-form">
        <a-form-item label="标题">
          <a-input v-model:value="title" :placeholder="`留空用默认：${DEFAULTS.title}`" maxlength="30" />
        </a-form-item>

        <a-form-item label="轮播图">
          <div class="upload-row">
            <a-upload
              :show-upload-list="false"
              :before-upload="uploadImage"
              accept="image/*"
              :disabled="uploading"
            >
              <div class="upload-btn" :class="{ 'is-busy': uploading }">
                <span class="up-plus">+</span>
                <span class="up-text">{{ uploading ? '上传中…' : '上传图片' }}</span>
              </div>
            </a-upload>
            <div v-for="(img, i) in images" :key="img.url" class="thumb-cell">
              <div class="banner-thumb">
                <img :src="img.url" alt="" />
                <span v-if="i === 0" class="main-tag">主图</span>
                <div class="thumb-ops">
                  <button type="button" class="op-copy" title="复制链接" @click="copyUrl(img.url)">⧉</button>
                  <button type="button" :disabled="i === 0" @click="moveImage(i, -1)" title="前移">←</button>
                  <button type="button" :disabled="i === images.length - 1" @click="moveImage(i, 1)" title="后移">→</button>
                  <button type="button" class="op-del" @click="removeImage(i)" title="删除">✕</button>
                </div>
              </div>
              <a-input
                v-model:value="img.subtitle"
                class="thumb-sub"
                size="small"
                placeholder="副标题（留空不显示）"
                maxlength="80"
              />
            </div>
          </div>

          <!-- 按链接添加（复用已上传图/外链图） -->
          <div class="add-url-row">
            <a-input-search
              v-model:value="addUrl"
              placeholder="粘贴图片链接加入轮播（本站 /api/server-catalog/model-image/... 或外部 http 图直链）"
              enter-button="添加"
              @search="addByUrl"
            />
          </div>

          <!-- 本站图片库：storage/model-images 全量文件（含机型主图/场景图），点击加入轮播 -->
          <div class="lib-sec">
            <div class="lib-title">本站图片库（{{ libImages.length }} 张，点图加入轮播，角标复制链接）</div>
            <div v-if="libImages.length" class="lib-grid">
              <div v-for="it in libImages" :key="it.filename" class="lib-thumb">
                <img :src="it.url" :title="it.filename" @click="appendImage(it.url)" />
                <button type="button" class="lib-copy" title="复制链接" @click.stop="copyUrl(it.url)">⧉</button>
                <span v-if="images.some(e => e.url === it.url)" class="lib-in-use">已在轮播</span>
              </div>
            </div>
            <div v-else class="hint">暂无已上传文件（上面「上传图片」后这里会出现）</div>
          </div>

          <div class="hint">
            多张图按顺序轮播（banner 两侧箭头左右滑动切换），首张为主图；每张图可在缩略图下方配独立副标题（随图切换展示，留空不显示）；不上传图时 banner 用内置银河星空场景。
          </div>
        </a-form-item>

        <a-button type="primary" :loading="saving" @click="save">保存</a-button>
      </a-form>
    </a-spin>
  </div>
</template>

<style scoped>
.panel { padding: 16px; margin-bottom: 16px; }
.lib-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.lib-head h3 { margin: 0; font-size: 15px; }
.hint { font-size: 12px; color: var(--cpq-text-muted, #6E7582); }

.banner-form { max-width: 640px; }

.upload-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; }
.upload-btn {
  width: 132px; height: 74px;
  border: 1px dashed var(--cpq-overlay-w25, rgba(255, 255, 255, 0.25));
  border-radius: 10px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; cursor: pointer;
  color: var(--cpq-text-secondary, #9BA1AA);
  transition: border-color .2s, color .2s;
}
.upload-btn:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.upload-btn.is-busy { opacity: .6; cursor: default; }
.up-plus { font-size: 20px; line-height: 1; }
.up-text { font-size: 12px; }

.thumb-cell { display: flex; flex-direction: column; gap: 4px; width: 132px; }

.banner-thumb {
  position: relative;
  width: 132px; height: 74px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, 0.1));
}
.banner-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.main-tag {
  position: absolute; top: 4px; left: 4px;
  font-size: 11px; padding: 1px 6px; border-radius: 999px;
  color: #fff; background: rgba(22, 119, 255, 0.85);
}
.thumb-ops {
  position: absolute; inset: auto 0 0 0;
  display: flex;
  background: rgba(0, 0, 0, 0.55);
}
.thumb-ops button {
  flex: 1;
  border: none; background: transparent;
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px; line-height: 22px;
  cursor: pointer;
}
.thumb-ops button:hover:not(:disabled) { background: rgba(255, 255, 255, 0.18); color: #fff; }
.thumb-ops button:disabled { opacity: .35; cursor: default; }
.thumb-ops .op-del:hover { background: rgba(255, 77, 79, 0.6); }
.thumb-ops .op-copy:hover { background: rgba(255, 255, 255, 0.18); }

.add-url-row { margin-top: 12px; max-width: 640px; }

.lib-sec { margin-top: 12px; }
.lib-title { font-size: 12px; color: var(--cpq-text-secondary, #9BA1AA); margin-bottom: 8px; }
.lib-grid { display: flex; flex-wrap: wrap; gap: 8px; max-width: 640px; }
.lib-thumb {
  position: relative;
  width: 104px; height: 58px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, 0.1));
  cursor: pointer;
  transition: border-color .2s, transform .2s;
}
.lib-thumb:hover { border-color: var(--cpq-accent-primary, #1677FF); transform: translateY(-1px); }
.lib-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.lib-copy {
  position: absolute; top: 3px; right: 3px;
  width: 20px; height: 20px;
  border: none; border-radius: 5px;
  background: rgba(0, 0, 0, 0.55);
  color: rgba(255, 255, 255, 0.9);
  font-size: 11px; line-height: 1;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.lib-copy:hover { background: rgba(0, 0, 0, 0.8); color: #fff; }
.lib-in-use {
  position: absolute; left: 3px; bottom: 3px;
  font-size: 10px; padding: 1px 5px; border-radius: 999px;
  color: #fff; background: rgba(22, 119, 255, 0.85);
  pointer-events: none;
}
</style>
