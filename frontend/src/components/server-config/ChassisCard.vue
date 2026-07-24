<script setup lang="ts">
/** 机箱概要卡片 — 配置页第 1 项 / 报价工作台机箱卡。
 *  卡头：标题 + 右侧 header-extra slot（报价页塞 PriceTriple 三联；配置页默认显 l6Total）。
 *  卡尾：基准配置(可选) + 配置机箱按钮。emit('open') 由父弹 4 步细配弹窗。 */
import CountNumber from '@/components/common/CountNumber.vue'
import type { ServerModel } from '@/api/serverConfig'

defineProps<{
  model: ServerModel
  series?: string
  baseConfigName?: string
  l6Total: number
  /** 卡头金额：传则显示售价(报价页)，不传回退 l6Total 成本(配置页) */
  heroPrice?: number
}>()

const emit = defineEmits<{ (e: 'open'): void }>()
</script>

<template>
  <div id="chassis-card" class="sc-panel chassis-card">
    <div class="sc-phead">
      <span class="num">1</span>
      <h2>机箱</h2>
      <div class="sc-phead-right">
        <slot name="header-extra">
          <span class="amt">¥<CountNumber :value="heroPrice ?? l6Total" /></span>
        </slot>
      </div>
    </div>
    <div class="sc-pbody">
      <div class="chassis-grid">
        <div class="ci"><span class="k">型号</span><span class="v name">{{ model.name }}</span></div>
        <div class="ci"><span class="k">机箱形态</span><span class="v">{{ model.base_config?.form || '—' }}</span></div>
        <div class="ci"><span class="k">芯片类型</span><span class="v arch">{{ series || '—' }}</span></div>
        <div class="ci"><span class="k">用途</span><span class="v">{{ model.use || '—' }}</span></div>
      </div>
      <div class="chassis-foot">
        <div class="chassis-bc" v-if="baseConfigName">
          <span class="bc-k">基准配置</span><span class="bc-v">{{ baseConfigName }}</span>
        </div>
        <slot name="foot-note" />
        <button class="chassis-config-btn" @click="emit('open')">配置机箱</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sc-panel {
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(16px);
  border: 1px solid var(--cpq-overlay-a15); border-radius: 18px; overflow: hidden;
  box-shadow: 0 22px 64px var(--cpq-shadow-color-strong), 0 0 34px var(--cpq-overlay-a4), inset 0 1px 0 var(--cpq-overlay-w15), inset 0 -18px 48px var(--cpq-shadow-color-soft);
}
.sc-phead { display: flex; align-items: center; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--cpq-overlay-w10); background: var(--cpq-overlay-w4); }
.sc-phead .num { width: 26px; height: 26px; border-radius: 7px; background: var(--cpq-overlay-a15); color: var(--cpq-accent-primary,#1677FF); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.sc-phead h2 { font-size: 16px; font-weight: 600; margin: 0; color: var(--cpq-text-primary, #E8ECEF); white-space: nowrap; }
.sc-phead-right { margin-left: auto; display: flex; align-items: center; gap: 14px; min-width: 0; }
.sc-phead .amt { color: var(--cpq-accent-primary,#1677FF); font-weight: 700; font-size: 14px; white-space: nowrap; }
.sc-pbody { padding: 18px 20px; }
.chassis-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.ci { padding: 12px 14px; background: var(--cpq-overlay-b20); border: 1px solid var(--cpq-overlay-w10); border-radius: 12px; }
.ci .k { display: block; font-size: 12px; color: var(--cpq-text-muted,#6E7582); margin-bottom: 4px; }
.ci .v { font-weight: 600; font-size: 15px; color: var(--cpq-text-primary, #E8ECEF); }
.ci .v.name { font-size: 16px; }
.ci .v.arch { color: var(--cpq-accent-primary,#1677FF); }
.chassis-foot { display: flex; align-items: center; gap: 16px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--cpq-overlay-w10); }
.chassis-bc { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.bc-k { font-size: 11px; color: var(--cpq-text-muted,#6E7582); }
.bc-v { font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary,#9BA1AA); }
.chassis-config-btn { margin-left: auto; padding: 8px 18px; border-radius: 9px; flex-shrink: 0;
  background: var(--cpq-overlay-a15); border: 1px solid var(--cpq-accent-primary,#1677FF);
  color: var(--cpq-accent-primary,#1677FF); font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; white-space: nowrap; }
.chassis-config-btn:hover { background: var(--cpq-accent-primary,#1677FF); color: var(--cpq-accent-on-primary); box-shadow: 0 0 18px var(--cpq-overlay-a40); transform: translateY(-1px); }
</style>
