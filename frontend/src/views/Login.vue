<template>
  <div class="login-page">
    <div class="login-card glass-strong">
      <div class="brand">
        <div class="logo-text">CPQ</div>
        <div class="logo-sub">Platform · 登录</div>
      </div>
      <a-form :model="form" layout="vertical" @finish="onFinish">
        <a-form-item label="用户名" name="username" :rules="[{ required: true, message: '请输入用户名' }]">
          <a-input v-model:value="form.username" placeholder="用户名" autocomplete="username" @press-enter="submit" />
        </a-form-item>
        <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
          <a-input-password v-model:value="form.password" placeholder="密码" autocomplete="current-password" @press-enter="submit" />
        </a-form-item>
        <a-button type="primary" block :loading="loading" html-type="submit">登 录</a-button>
      </a-form>
      <div class="login-tip">首次使用请用引导管理员账号登录，登录后可在「用户与权限」修改密码。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function onFinish() {
  await submit()
}

async function submit() {
  if (!form.username.trim() || !form.password) return
  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || e?.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  width: 100vw;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cpq-bg-primary, #0f1216);
  overflow: hidden;
}
.login-card {
  width: 360px;
  padding: 32px 28px 24px;
  border-radius: 16px;
}
.brand {
  text-align: center;
  margin-bottom: 24px;
}
.logo-text {
  font-size: 30px;
  font-weight: 700;
  color: var(--cpq-accent-primary, #1677ff);
  letter-spacing: 3px;
  line-height: 1;
}
.logo-sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--cpq-text-secondary, #9ba1aa);
  letter-spacing: 1px;
}
.login-tip {
  margin-top: 16px;
  font-size: 12px;
  color: var(--cpq-text-muted, #6e7582);
  text-align: center;
  line-height: 1.6;
}
</style>
