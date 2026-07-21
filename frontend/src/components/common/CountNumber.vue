<template>
  <span class="cpq-count">{{ Math.round(display).toLocaleString() }}</span>
</template>

<script setup lang="ts">
import { useCountUp } from '@/composables/useCountUp'

const props = defineProps<{ value: number; duration?: number }>()
const display = useCountUp(() => props.value, props.duration ?? 900)
</script>
