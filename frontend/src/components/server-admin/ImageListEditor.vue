<script setup lang="ts">
/** 图片列表编辑器（共享件）— 上传/粘贴链接/排序/删除/复制链接，v-model 绑定 PortalBannerImage[]。
 *  消费方：门户 banner 轮播设置（subtitle-mode 带副标题框）、机型编辑页多视角图库。
 *  图片复用 /models/image 内容寻址池（同内容幂等去重）；已有图片到管理面「图片资产」tab 复制链接后粘贴。 */
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import type { PortalBannerImage } from '@/api/serverConfig'
import { copyText } from '@/utils/clipboard'

const props = withDefaults(defineProps<{
  modelValue: PortalBannerImage[]
  /** 上传图片的用途标记（内容寻址池仅作记录）：portal-banner / product 等 */
  uploadType?: string
  /** 缩略图下显示副标题输入框（门户 banner 随图切换展示） */
  subtitleMode?: boolean
}>(), { uploadType: 'portal-banner', subtitleMode: false })

const emit = defineEmits<{ (e: 'update:modelValue', v: PortalBannerImage[]): void }>()

function commit(v: PortalBannerImage[]) { emit('update:modelValue', v) }

async function uploadImage(file: File): Promise<boolean> {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await axios.post('/api/server-catalog/models/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { type: props.uploadType },
    })
    commit([...props.modelValue, { url: resp.data.url }])
    message.success('已上传，保存后生效')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  } finally { uploading.value = false }
  return false
}
const uploading = ref(false)

/** 复制图片链接（站内相对路径补全为绝对 URL，站外也能直接用） */
function copyUrl(url: string) {
  copyText(url, { absolute: true, successMsg: '链接已复制' })
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
  if (props.modelValue.some(e => e.url === url)) {
    message.warning('该图片已在列表中')
    return
  }
  commit([...props.modelValue, { url }])
  message.success('已加入列表，保存后生效')
}

function removeImage(i: number) {
  const v = [...props.modelValue]
  v.splice(i, 1)
  commit(v)
}
function moveImage(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= props.modelValue.length) return
  const v = [...props.modelValue]
  const [item] = v.splice(i, 1)
  v.splice(j, 0, item)
  commit(v)
}
</script>

<template>
  <div class="ile-root">
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
      <div v-for="(img, i) in modelValue" :key="img.url" class="thumb-cell">
        <div class="ile-thumb">
          <img :src="img.url" alt="" />
          <span v-if="i === 0" class="main-tag">主图</span>
          <div class="thumb-ops">
            <button type="button" class="op-copy" title="复制链接" @click="copyUrl(img.url)">⧉</button>
            <button type="button" :disabled="i === 0" @click="moveImage(i, -1)" title="前移">←</button>
            <button type="button" :disabled="i === modelValue.length - 1" @click="moveImage(i, 1)" title="后移">→</button>
            <button type="button" class="op-del" @click="removeImage(i)" title="删除">✕</button>
          </div>
        </div>
        <a-input
          v-if="subtitleMode"
          v-model:value="img.subtitle"
          class="thumb-sub"
          size="small"
          placeholder="副标题（留空不显示）"
          maxlength="80"
        />
      </div>
    </div>

    <!-- 按链接添加（复用已上传图/外链图；已有图片到「图片资产」tab 复制链接） -->
    <div class="add-url-row">
      <a-input-search
        v-model:value="addUrl"
        placeholder="粘贴图片链接加入列表（本站 /api/server-catalog/model-image/... 或外部 http 图直链）"
        enter-button="添加"
        @search="addByUrl"
      />
      <div class="ile-hint">已有图片可在管理面「图片资产」tab 搜索/复制链接后粘贴到上面</div>
    </div>
  </div>
</template>

<style scoped>
.ile-root { width: 100%; }
.ile-hint { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted, #6E7582); }

.upload-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; }
.upload-btn {
  width: 132px; height: 74px;
  border: 1px dashed var(--cpq-glass-border);
  border-radius: var(--cpq-radius-md);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; cursor: pointer;
  color: var(--cpq-text-secondary, #9BA1AA);
  transition: border-color .2s, color .2s;
}
.upload-btn:hover { border-color: var(--cpq-accent-primary, #1677FF); color: var(--cpq-accent-primary, #1677FF); }
.upload-btn.is-busy { opacity: .6; cursor: default; }
.up-plus { font-size: var(--cpq-font-size-xl); line-height: 1; }
.up-text { font-size: var(--cpq-font-size-sm); }

.thumb-cell { display: flex; flex-direction: column; gap: 4px; width: 132px; }

.ile-thumb {
  position: relative;
  width: 132px; height: 74px;
  border-radius: var(--cpq-radius-md);
  overflow: hidden;
  border: 1px solid var(--cpq-glass-border);
}
.ile-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.main-tag {
  position: absolute; top: 4px; left: 4px;
  font-size: var(--cpq-font-size-xs); padding: 1px 6px; border-radius: var(--cpq-radius-full);
  color: #fff; background: rgba(22, 119, 255, 0.85);
}
.thumb-ops {
  position: absolute; top: 4px; right: 4px;
  display: flex; gap: 4px;
}
.thumb-ops button {
  width: 22px; height: 22px;
  border: none; border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: rgba(255, 255, 255, 0.9);
  font-size: var(--cpq-font-size-xs); line-height: 1;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
}
.thumb-ops button:hover:not(:disabled) { background: rgba(255, 255, 255, 0.18); color: #fff; }
.thumb-ops button:disabled { opacity: .35; cursor: default; }
.thumb-ops .op-del:hover { background: rgba(255, 77, 79, 0.6); }
.thumb-ops .op-copy:hover { background: rgba(255, 255, 255, 0.18); }

.add-url-row { margin-top: 12px; max-width: 640px; }
</style>
