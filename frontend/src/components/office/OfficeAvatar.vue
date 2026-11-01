<template>
  <span
    class="oa"
    :class="{ 'is-photo': !!url }"
    :style="{
      width: size + 'px',
      height: size + 'px',
      fontSize: Math.round(props.size * 0.42) + 'px',
      '--oa-ring': accent || undefined,
      '--oa-tint': accent ? accent + '29' : undefined,
    }"
  >
    <img v-if="url" :src="url" alt="" />
    <span v-else class="oa-fb" :style="{ background: color }">{{ initial }}</span>
  </span>
</template>

<script setup lang="ts">
/* 办公室统一头像（悬停卡/右栏名册/移动头像行共用）：
   档案头像 URL > Live2D 形象快照（getLive2dSnapshot 按 model 缓存，多实例共用一次生成）> 色块首字 */
import { computed, onMounted, ref } from 'vue'
import { getLive2dSnapshot } from '@/utils/l2dSnapshot'

const props = withDefaults(defineProps<{
  colleague: any | null
  size?: number
}>(), { size: 28 })

const snap = ref<string | null>(null)

const url = computed(() => props.colleague?.avatar_url || snap.value || '')
const color = computed(() => props.colleague?.color || '#1677ff')
const accent = computed(() => props.colleague?.color || '')
const initial = computed(() => {
  const text = (props.colleague?.name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
})

onMounted(async () => {
  const model = props.colleague?.pet_model || 'koharu'
  if (props.colleague?.avatar_url) return
  snap.value = await getLive2dSnapshot(model)
})
</script>

<style scoped>
.oa {
  display: inline-grid;
  place-items: center;
  flex: none;
  border-radius: 50%;
  overflow: hidden;
  background: var(--cpq-glass-2-bg, rgba(255, 255, 255, 0.09));
}
/* 快照模式 = 档案页设计：主题色描边 + 淡主题色底 */
.oa.is-photo {
  border: 2px solid var(--oa-ring, var(--cpq-glass-border, rgba(255, 255, 255, 0.11)));
  background: var(--oa-tint, var(--cpq-glass-2-bg, rgba(255, 255, 255, 0.09)));
}
.oa img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.oa-fb {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--cpq-accent-on-primary, #fff);
  font-weight: 700;
  line-height: 1;
}
</style>
