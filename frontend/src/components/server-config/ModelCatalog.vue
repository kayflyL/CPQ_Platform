<script setup lang="ts">
/** 服务器类型选择（配置面第一层）— 点击类型卡片跳转到 /servers/types/:typeId */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { catalogApi, type ServerType } from '@/api/serverConfig'

const router = useRouter()
const types = ref<ServerType[]>([])
const loading = ref(false)

async function loadTypes() {
  loading.value = true
  try {
    types.value = (await catalogApi.listTypes()).types
  } catch (e: any) {
    console.error('加载类型失败', e)
  } finally { loading.value = false }
}

function goToModels(type: ServerType) {
  router.push(`/servers/types/${type.id}`)
}

onMounted(loadTypes)
</script>

<template>
  <div class="sc-catalog">
    <h2 class="sc-title">配置一台服务器</h2>
    <p class="sc-sub">选择用途，挑机型，进入四步配置。背板类型与 GPU 架构在配置中确定。</p>

    <div class="sc-types" v-if="types.length">
      <div v-for="t in types" :key="t.id" class="sc-type-card" @click="goToModels(t)">
        <div class="tn">{{ t.name }}</div>
        <div class="td">{{ t.description }}</div>
        <div class="tm"><span>选择机型 →</span></div>
      </div>
    </div>
    <div v-else-if="!loading" class="sc-empty">暂无服务器类型，请联系管理员。</div>
  </div>
</template>

<style scoped>
.sc-catalog {
  max-width: 1180px;
  margin: 0 auto;
}
.sc-title { font-size: 22px; font-weight: 600; margin-bottom: 4px; }
.sc-sub { color: var(--cpq-text-secondary, #9BA1AA); font-size: 14px; margin-bottom: 24px; }

.sc-types { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
.sc-type-card {
  position: relative; padding: 28px 24px;
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 18px; cursor: pointer;
  transition: all .3s cubic-bezier(.16,1,.3,1); overflow: hidden;
  background: linear-gradient(135deg,
    rgba(255,255,255,0.07) 0%,
    rgba(255,255,255,0.03) 40%,
    rgba(8,12,16,0.25) 100%);
  backdrop-filter: blur(16px) saturate(1.4);
  box-shadow:
    0 22px 64px rgba(0,0,0,0.30),
    0 0 34px rgba(0,245,212,0.04),
    inset 0 1px 0 rgba(255,255,255,0.13),
    inset 0 -18px 48px rgba(0,0,0,0.14);
}
.sc-type-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--cpq-accent-primary,#00F5D4); opacity: 0; transition: opacity .3s;
}
.sc-type-card:hover {
  border-color: rgba(0,245,212,.3);
  transform: translateY(-2px);
  box-shadow:
    0 22px 64px rgba(0,0,0,0.30),
    0 0 34px rgba(0,245,212,0.12),
    inset 0 1px 0 rgba(255,255,255,0.13),
    inset 0 -18px 48px rgba(0,0,0,0.14);
}
.sc-type-card:hover::before { opacity: 1; }
.sc-type-card .tn { font-size: 18px; font-weight: 600; margin-bottom: 8px; color: var(--cpq-text-primary, #E8ECEF); }
.sc-type-card .td { font-size: 14px; color: var(--cpq-text-secondary,#9BA1AA); min-height: 40px; line-height: 1.5; }
.sc-type-card .tm {
  margin-top: 18px; padding-top: 14px;
  border-top: 1px solid rgba(255,255,255,.10);
  font-size: 13px; color: var(--cpq-text-muted,#6E7582);
  transition: color .2s;
}
.sc-type-card:hover .tm { color: var(--cpq-accent-primary,#00F5D4); }
.sc-empty { color: var(--cpq-text-muted,#6E7582); text-align: center; padding: 50px; font-size: 14px; }
</style>
