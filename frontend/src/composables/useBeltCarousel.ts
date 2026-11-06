import { ref, watch, nextTick, type Ref } from 'vue'

/**
 * 传送带轮播（服务器目录 banner 同款，详情页 hero 共用）。
 *
 * 方向纯按钮驱动（传送带恒向）：点左箭头旧图永远向左驶离、新图从右边缘驶入；不随循环索引回弹换向。
 * 偏移单位是「格」（每格=消费方 CSS 里的一屏宽，如 110vw / 110%），±1 格即画面外；
 * pendingIdx 标记正被无动画瞬移到入场侧的图（消费方加 no-anim 类禁掉过渡）。
 */
export function useBeltCarousel(count: Ref<number>) {
  const slideIdx = ref(0)
  const slideOffsets = ref<number[]>([0])       // 每张图的轨道偏移（格数；0=主位）
  const pendingIdx = ref<number | null>(null)   // 正被无动画瞬移到入场侧的图
  let shifting = false                          // 瞬移窗口内防重入（连点会让两次起点竞态）
  watch(count, (n) => {
    slideIdx.value = 0
    slideOffsets.value = Array.from({ length: n }, (_, i) => (i === 0 ? 0 : i))   // 其余先停到画面外
    pendingIdx.value = null
  }, { immediate: true })

  async function shiftSlide(belt: 1 | -1) {     // belt=带移动方向：+1=右箭头(旧图右驶离,新图自左驶入)，-1=左箭头镜像
    const n = count.value
    if (n < 2 || shifting) return
    shifting = true
    try {
      const target = (slideIdx.value - belt + n) % n
      pendingIdx.value = target
      slideOffsets.value[target] = -belt               // 入场图瞬移到入场侧（驶离方向的对侧）
      await nextTick()
      // 双 rAF：等浏览器真的绘出瞬移位置。nextTick 只是微任务，若同帧改回主位，
      // 两次样式合并成一帧，过渡起点回落到上次绘制位置 → 旧图从错侧滑回、两图交织
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
      pendingIdx.value = null
      slideIdx.value = target
      slideOffsets.value = slideOffsets.value.map((o, i) =>
        i === target ? 0 : o + belt,                   // 入场图滑入主位；其余（含旧主图）向 belt 侧挪一格驶离
      )
    } finally { shifting = false }
  }
  const prevSlide = () => shiftSlide(-1)
  const nextSlide = () => shiftSlide(1)
  return { slideIdx, slideOffsets, pendingIdx, shiftSlide, prevSlide, nextSlide }
}
