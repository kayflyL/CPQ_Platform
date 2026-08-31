<script setup lang="ts">
/** 解决方案门户(/strategies)—— 两排结构。
 *  第一排:需求分析 / 选型配置 / 报价策略 模块卡;
 *  第二排:解决方案库(按场景分类的方案卡片 + 独立详情页)。 */
import { useRouter } from 'vue-router'
import SolutionLibrary from './strategy/SolutionLibrary.vue'

const router = useRouter()

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
    desc: '需求明确度、平台系列、RAID/规格等规则目录，固定专家流程',
    tags: ['业务输入', '场景定义'],
    to: '/strategies/requirement',
  },
  {
    key: 'selection',
    title: '选型配置',
    desc: '配件互斥 / 依赖 / 派生硬规则 + BOM案例库(典型配置方案,按系列/平台/机型分类,需求分析可作推荐参考)',
    tags: ['规则校验', '多平台匹配'],
    to: '/strategies/selection',
  },
  {
    key: 'pricing',
    title: '报价策略',
    desc: '加法定价引擎(平台+行业+区域×订单×成本×台数)',
    tags: ['成本定价', '批量报价'],
    to: '/strategies/pricing',
  },
]

function enter(m: ModuleCard) { router.push(m.to) }
</script>

<template>
  <div class="portal">
    <header class="portal-head">
      <h1 class="portal-title">解决方案</h1>
      <p class="portal-sub">从需求到报价，按场景沉淀可复用的服务器方案。</p>
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
          </div>
        </div>
        <p class="mc-desc">{{ m.desc }}</p>
        <div class="mc-tags">
          <span v-for="t in m.tags" :key="t" class="mc-tag">{{ t }}</span>
        </div>
        <div class="mc-enter">进入 <span class="mc-arrow">→</span></div>
      </div>
    </div>

    <SolutionLibrary />
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

.mod-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 20px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: 14px;
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  -webkit-backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.mod-card.is-clickable { cursor: pointer; }
.mod-card.is-clickable:hover {
  border-color: var(--cpq-glass-border-strong);
  transform: translateY(-2px);
  box-shadow: var(--cpq-glass-card-shadow-hover);
}

.mc-head { display: flex; align-items: center; gap: 14px; }
.mc-title-block { min-width: 0; }
.mc-title { font-size: 18px; font-weight: 700; color: var(--cpq-text-primary); }
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
