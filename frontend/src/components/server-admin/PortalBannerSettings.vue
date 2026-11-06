<script setup lang="ts">
/** 门户设置 — 服务器门户 banner 标题 + 轮播图管理（system_config.server_portal_banner）。
 *  标题留空=门户回落内置默认；每张轮播图可配独立副标题（门户随图切换展示，留空不显示）。
 *  图片管理交互在共享件 ImageListEditor（机型编辑页多视角图库同款）。 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { catalogApi, type PortalBannerImage } from '@/api/serverConfig'
import ImageListEditor from '@/components/server-admin/ImageListEditor.vue'

const DEFAULTS = {
  title: '配置一台服务器',
}

const title = ref('')
const images = ref<PortalBannerImage[]>([])
const loading = ref(false)
const saving = ref(false)

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
})
</script>

<template>
  <div class="portal-banner-settings">
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
          <ImageListEditor v-model="images" upload-type="portal-banner" subtitle-mode />
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
.lib-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.lib-head h3 { margin: 0; font-size: 17px; font-weight: 700; }
.hint { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted, #6E7582); }

.banner-form { max-width: 640px; }
</style>
