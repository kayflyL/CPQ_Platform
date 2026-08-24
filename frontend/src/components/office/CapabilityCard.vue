<template>
  <article
    class="cc-card"
    :class="{ 'cc-card--bound': bound, 'cc-card--disabled': !skill.runnable }"
    @click="$emit('detail', skill)"
  >
    <header class="cc-head">
      <div class="cc-title">
        <strong>{{ skill.name || skill.key }}</strong>
        <a-tag v-if="bound" color="green">已绑定</a-tag>
        <a-tag v-if="skill.runnable" color="blue">可试运行</a-tag>
      </div>
      <span class="cc-arrow">›</span>
    </header>
    <p class="cc-desc">{{ skill.description || '暂无说明' }}</p>
    <div class="cc-tags">
      <a-tag v-for="tool in skill.tool_ids || []" :key="tool" color="purple">{{ tool }}</a-tag>
    </div>
    <footer class="cc-foot">
      <span v-if="skill.runtime_name">{{ skill.runtime_name }}</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  skill: any
  bound?: boolean
}>()

defineEmits<{ (e: 'detail', skill: any): void }>()
</script>

<style scoped>
.cc-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, 0.1));
  border-radius: 12px;
  background: var(--cpq-overlay-w5, rgba(255, 255, 255, 0.05));
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  min-height: 118px;
}
.cc-card:hover {
  border-color: var(--cpq-accent-primary);
  box-shadow: var(--cpq-shadow-md);
  transform: translateY(-1px);
}
.cc-card--bound {
  border-color: rgba(82, 196, 26, 0.45);
}
.cc-card--disabled {
  cursor: default;
}
.cc-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.cc-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.cc-title strong {
  color: var(--cpq-text-primary);
  font-size: 14px;
}
.cc-arrow {
  color: var(--cpq-text-muted);
  font-size: 18px;
  line-height: 1;
}
.cc-desc {
  margin: 0;
  min-height: 32px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.cc-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 22px;
}
.cc-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--cpq-text-muted);
  font-size: 11px;
}
</style>
