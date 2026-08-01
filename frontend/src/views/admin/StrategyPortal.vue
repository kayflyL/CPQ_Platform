<script setup lang="ts">
/** 策略中心门户(/strategies)—— 模块卡片入口,对标服务器配置门户(ServerModelCard 同款白玻璃卡)。
 *  点卡进入各模块:报价策略(工作台) / 选型配置 / 需求分析(后两者暂直跳编辑器,有文档后升级同款工作台)。
 *  卡片统一白玻璃 + hover 蓝边,不分模块配色(Glass Console:色彩只给语义态)。 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { strategyApi } from '@/api/strategies'

const router = useRouter()
const pricingDocCount = ref<number | null>(null)

interface ModuleCard {
  key: string
  title: string
  desc: string
  tags: string[]
  to: string
}

const MODULES: ModuleCard[] = [
  {
    key: 'requirement',
    title: '需求分析',
    desc: 'BOM 推理流可视化编排:提取需求 → 明确度反问 → 选 baseline → 配 KP → 组方案',
    tags: ['推理流 DAG', 'CRE 规则库', '图驱动 executor'],
    to: '/strategies/requirement',
  },
  {
    key: 'selection',
    title: '选型配置',
    desc: '配件互斥 / 依赖 / 派生硬规则,工作台选配时实时校验(建议层,只警告不锁)',
    tags: ['CRE 规则引擎', 'WHEN→THEN', '声明式'],
    to: '/strategies/selection',
  },
  {
    key: 'pricing',
    title: '报价策略',
    desc: '加法定价引擎(平台+行业+区域×订单×成本×台数)+ 策略文档库定价手册',
    tags: ['画布 + 演算器', '策略文档库', '加法引擎'],
    to: '/strategies/pricing',
  },
]

function enter(m: ModuleCard) { router.push(m.to) }

onMounted(async () => {
  try {
    const res = await strategyApi.listDocs()
    pricingDocCount.value = res.strategies?.length ?? 0
  } catch { /* 文档数非关键,失败静默 */ }
})
</script>

<template>
  <div class="portal">
    <header class="portal-head">
      <h1 class="portal-title">策略中心</h1>
      <p class="portal-sub">定价 · 选型 · 推理 三域规则统一治理。点卡片进入对应模块。</p>
    </header>

    <div class="portal-grid">
      <div
        v-for="m in MODULES"
        :key="m.key"
        class="mod-card is-clickable"
        @click="enter(m)"
      >
        <div class="mc-head">
          <div class="mc-title-block">
            <div class="mc-title">{{ m.title }}</div>
            <div v-if="m.key === 'pricing' && pricingDocCount !== null" class="mc-badge">
              {{ pricingDocCount }} 篇文档
            </div>
          </div>
        </div>
        <p class="mc-desc">{{ m.desc }}</p>
        <div class="mc-tags">
          <span v-for="t in m.tags" :key="t" class="mc-tag">{{ t }}</span>
        </div>
        <div class="mc-enter">进入 <span class="mc-arrow">→</span></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.portal { max-width: 1180px; margin: 0 auto; padding: 8px 24px 80px; }
.portal-head { margin-bottom: 28px; padding-top: 8px; }
.portal-title { font-size: 24px; font-weight: 700; color: var(--cpq-text-primary); margin: 0 0 6px; }
.portal-sub { font-size: 13.5px; color: var(--cpq-text-muted); margin: 0; }

.portal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 18px;
}

/* 卡片:镜像 ServerModelCard 白玻璃配方(统一服务器那边) */
.mod-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 10px 30px var(--cpq-shadow-color-soft), inset 0 1px 0 var(--cpq-overlay-w15);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.mod-card.is-clickable { cursor: pointer; }
.mod-card.is-clickable:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-2px);
  box-shadow: 0 16px 40px var(--cpq-shadow-color-strong), inset 0 1px 0 var(--cpq-overlay-w15);
}

.mc-head { display: flex; align-items: center; gap: 14px; }
.mc-title-block { min-width: 0; }
.mc-title { font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); }
.mc-badge {
  display: inline-block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a10);
  padding: 1px 8px;
  border-radius: 8px;
}
.mc-desc {
  font-size: 13px;
  color: var(--cpq-text-secondary);
  line-height: 1.6;
  margin: 0;
  flex: 1;
}
.mc-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.mc-tag {
  font-size: 11px;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w6);
  padding: 2px 9px;
  border-radius: 10px;
}
.mc-enter {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-accent-primary);
  display: flex;
  align-items: center;
  gap: 4px;
}
.mc-arrow { transition: transform 0.18s ease; }
.mod-card:hover .mc-arrow { transform: translateX(4px); }
</style>
