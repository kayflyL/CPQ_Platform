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
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-xl); cursor: pointer;
  transition: all .3s var(--cpq-ease-out-expo); overflow: hidden;
  background: linear-gradient(135deg, var(--cpq-glass-1-bg) 0%, var(--cpq-glass-2-bg) 100%);
  backdrop-filter: blur(var(--cpq-glass-blur-1));
  -webkit-backdrop-filter: blur(var(--cpq-glass-blur-1));
  box-shadow: var(--cpq-shadow-md), inset 0 1px 0 var(--cpq-glass-highlight);
}
.sc-type-card:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-3px);
  background: linear-gradient(135deg, var(--cpq-glass-2-bg) 0%, var(--cpq-glass-1-bg) 100%);
  box-shadow: var(--cpq-shadow-lg), 0 0 0 1px var(--cpq-overlay-a15), inset 0 1px 0 var(--cpq-glass-highlight);
}
.sc-type-card:hover .tn { color: var(--cpq-accent-primary); }
.sc-type-card .tn { font-size: 18px; font-weight: 600; margin-bottom: 8px; color: var(--cpq-text-primary, #E8ECEF); }
.sc-type-card .td { font-size: 14px; color: var(--cpq-text-secondary,#9BA1AA); min-height: 40px; line-height: 1.5; }
.sc-type-card .tm {
  margin-top: 18px; padding-top: 14px;
  border-top: 1px solid var(--cpq-overlay-w10);
  font-size: 13px; color: var(--cpq-text-muted,#6E7582);
  transition: color var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.sc-type-card .tm span { display: inline-block; transition: transform var(--cpq-dur-2) var(--cpq-ease-smooth); }
.sc-type-card:hover .tm { color: var(--cpq-accent-primary); }
.sc-type-card:hover .tm span { transform: translateX(4px); }
.sc-empty { color: var(--cpq-text-muted,#6E7582); text-align: center; padding: 50px; font-size: 14px; }
</style>
