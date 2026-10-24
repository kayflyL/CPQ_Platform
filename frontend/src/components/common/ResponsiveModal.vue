<script setup lang="ts">
/**
 * 移动端自适应弹窗（modalPresets 桌面口径的移动形态）。
 * 段位策略：桌面 = a-modal + MODAL_WIDTH 档位宽（与直接用 a-modal 无差别）；
 * ≤768px：sheet/viewer/full 级转全屏页——左上角返回按钮 + 系统返回手势同步。
 * 轻量 action 小表单不转全屏 :fullscreen="false"。
 * 注意：title 请用属性传入（本项目所有调用点都是属性传法），不要用 #title 插槽。
 */
import { computed, onBeforeUnmount, useAttrs, watch } from 'vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { useFullscreenModalHistory } from '@/composables/fullscreenModalHistory'
import { MODAL_WIDTH, type ModalWidthTier } from '@/constants/modalPresets'

const props = withDefaults(defineProps<{ open: boolean; tier?: ModalWidthTier; fullscreen?: boolean }>(), {
  tier: 'sheet',
  fullscreen: true,
})
// 必须关闭属性透传：否则调用方的 wrap-class-name 会在根节点上覆盖我们的合并值（Vue 透传优先）
defineOptions({ inheritAttrs: false })

const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'cancel'): void }>()

const attrs = useAttrs()
const isMobile = useIsMobile()
const isFull = computed(() => isMobile.value && props.fullscreen)
// 全屏态不给 width（由 .cpq-fs-modal 的四边钉死 + 拉伸接管）：
// 100vw 在带滚动条的桌面包含滚动条宽，会顶出横向缝隙
const width = computed(() => (isFull.value ? undefined : MODAL_WIDTH[props.tier]))

// 调用方自带的 wrap-class-name（如 portal-sheet-modal）与全屏类名合并；width/closable 由本组件接管。
// 注意必须从透传 attrs 里剥掉冲突键：实测 v-bind="$attrs" 会盖过同名的显式绑定。
const forwardAttrs = computed(() => {
  const strip = new Set(['wrap-class-name', 'wrapClassName', 'width', 'closable'])
  // 手机全屏时标题交给 #title 插槽（带返回按钮）；antd-vue 在有 title prop 时会无视插槽，必须剥掉
  if (isFull.value) strip.add('title')
  const rest: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(attrs)) {
    if (strip.has(k)) continue
    rest[k] = v
  }
  return rest
})
const mergedWrapCls = computed(() =>
  [String(attrs['wrap-class-name'] || attrs.wrapClassName || ''), isFull.value ? 'cpq-fs-modal' : '']
    .filter(Boolean).join(' '))

function doClose() {
  emit('update:open', false)
  emit('cancel')
}

const { push, release } = useFullscreenModalHistory()
let histId = 0

watch(() => props.open, (v) => {
  if (!isFull.value) return
  if (v && !histId) histId = push(doClose)
  else if (!v && histId) {
    release(histId)
    histId = 0
  }
})

// 桌面↔手机切换（转屏/拉窗口）时退出全屏态：清历史栈
watch(isFull, (v) => {
  if (!v && histId) {
    release(histId)
    histId = 0
  }
})

onBeforeUnmount(() => {
  if (histId) {
    release(histId)
    histId = 0
  }
})

/** 关闭统一入口：全屏态走历史回退（popstate 回调里收弹窗），桌面直接关 */
function closeViaUi() {
  if (histId) {
    release(histId)
    histId = 0
  } else {
    doClose()
  }
}
</script>

<template>
  <a-modal
    v-bind="forwardAttrs"
    :open="open"
    :width="width"
    :wrap-class-name="mergedWrapCls"
    :closable="!isFull"
    @cancel="closeViaUi"
  >
    <template v-if="isFull" #title>
      <div class="cpq-fs-head">
        <button class="cpq-fs-back" type="button" aria-label="返回" @click="closeViaUi">
          <ArrowLeftOutlined />
        </button>
        <span class="cpq-fs-head-title">{{ typeof $attrs.title === 'string' ? $attrs.title : '' }}</span>
      </div>
    </template>
    <template v-for="(_, name) in $slots" :key="name" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps ?? {}" />
    </template>
  </a-modal>
</template>

