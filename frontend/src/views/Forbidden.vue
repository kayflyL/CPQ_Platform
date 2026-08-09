<template>
  <div class="forbidden">
    <div class="fb-card glass-strong">
      <div class="fb-code">403</div>
      <div class="fb-title">无权访问</div>
      <div class="fb-desc">当前账号没有访问该页面的权限，请联系管理员分配角色。</div>
      <a-button type="primary" @click="router.push('/')">返回首页</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<style scoped>
.forbidden {
  height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cpq-bg-primary, #0f1216);
}
.fb-card {
  padding: 40px 48px;
  border-radius: 16px;
  text-align: center;
}
.fb-code {
  font-size: 48px;
  font-weight: 800;
  color: var(--cpq-accent-primary, #1677ff);
}
.fb-title {
  margin: 8px 0 4px;
  font-size: 18px;
  color: var(--cpq-text-primary, #e8ecef);
}
.fb-desc {
  margin-bottom: 20px;
  font-size: 13px;
  color: var(--cpq-text-secondary, #9ba1aa);
}
</style>
