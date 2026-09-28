<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'

/** 星河首页（/galaxy）—— 静态星河页以 iframe 内嵌，保留顶栏导航。
 *  融合手法：外层容器整屏深空底色（与星河页背景同色），顶栏让位带透出同一深色；
 *  hero-dark 让顶栏文字用浅色 token。
 *  星河页点击机型详情时 postMessage 过来，这里弹居中模态内嵌**真实详情页**（iframe 整页搬入，
 *  样式内容与 /servers/models/:id 完全一致），关闭即回到星河，无页面跳转。 */

// 星河页版本号：变更星河页内容时递增，强制浏览器拉新（防旧缓存）

function markHeroDark(on: boolean) {
  if (on) document.documentElement.dataset.heroDark = '1'
  else delete document.documentElement.dataset.heroDark
}

const modalOpen = ref(false)
const modelId = ref<number | null>(null)

// 星河页 src 只在挂载时定死（每次进入页面取新时间戳防旧缓存）；弹窗开合会重渲染本组件，
// 若 src 写在模板里每次重渲染都会换 t= 触发 iframe 整页重载（星河被打回 loader 进入页）
const galaxySrc = `/galaxy/index.html?t=${Date.now()}`

function onMessage(e: MessageEvent) {
  const d = e.data as { type?: string; id?: number } | null
  if (d && d.type === 'xq:open-model' && d.id) {
    modelId.value = d.id
    modalOpen.value = true
  }
}

onMounted(() => {
  markHeroDark(true)
  document.documentElement.style.setProperty('--hero-band-bg', 'rgba(1, 3, 10, 0.82)')
  window.addEventListener('message', onMessage)
})
onBeforeUnmount(() => {
  markHeroDark(false)
  document.documentElement.style.removeProperty('--hero-band-bg')
  window.removeEventListener('message', onMessage)
})
</script>

<template>
  <div class="galaxy-home">
    <iframe
      class="galaxy-frame"
      :src="galaxySrc"
      title="星河首页"
    />
  </div>
  <a-modal
    v-model:open="modalOpen"
    :footer="null"
    centered
    destroy-on-close
    wrap-class-name="galaxy-model-modal"
    width="min(1200px, 94vw)"
    style="top: 40px"
  >
    <template #title>
      <span class="gmm-title">服务器详情</span>
    </template>
    <!-- 真实详情页整页嵌入：样式/内容与 /servers/models/:id 完全一致 -->
    <iframe
      v-if="modelId"
      class="gmm-frame"
      :src="`/servers/models/${modelId}`"
      :title="'服务器详情'"
    />
  </a-modal>
</template>

<style scoped>
/* 整屏深空底：顶栏让位带透出的就是这一层，与 iframe 内星河背景同色无缝 */
.galaxy-home {
  margin-top: calc(-1 * var(--cpq-header-clearance, 72px));
  height: 100vh;
  background: #01030a;
  overflow: hidden;
}
.galaxy-frame {
  display: block;
  width: 100%;
  /* 让位带以下才开始真正的星河页，页内元素坐标保持独立设计不与顶栏互扰 */
  height: calc(100% - var(--cpq-header-clearance, 72px));
  margin-top: var(--cpq-header-clearance, 72px);
  border: none;
  background: #01030a;
}
.gmm-frame {
  display: block;
  width: 100%;
  height: calc(88vh - 110px);
  min-height: 480px;
  border: none;
  background: #050b18;
}
.gmm-title { color: #eef3fa; letter-spacing: 0.2em; font-size: 15px; }
</style>

<style>
/* 模态挂载在 body 下（teleport），需非 scoped 覆盖 */
.galaxy-model-modal .ant-modal-content { background: #050b18; padding: 12px 16px 16px; }
.galaxy-model-modal .ant-modal-header { background: transparent; }
.galaxy-model-modal .ant-modal-close { color: rgba(238, 243, 250, 0.6); }
.galaxy-model-modal .ant-modal-close:hover { color: #fff; }
.galaxy-model-modal .ant-modal-title { color: #eef3fa; }
</style>
