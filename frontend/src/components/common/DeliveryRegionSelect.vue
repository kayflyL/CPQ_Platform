<script setup lang="ts">
/**
 * 交付地区选择器（共享）—— 两段折叠面板：顶层只有「国内 / 海外 / 不在列表中」，
 * 点国内展开省级 chips，点海外展开大洲、再点大洲展开国家 chips。
 * 触发钮恒显原始值文本：商机详情页存量自由文本（国内/上海/东南亚…）回显不丢，
 * 重新选择后才收敛为编码值（国内-广东 / 海外-日本 / 海外-不在列表中）。
 * 数据源 constants/regions.ts（唯一来源，/lead 公开表单与商机详情页两个入口共用）。
 */
import { ref, watch } from 'vue'
import { DownOutlined } from '@ant-design/icons-vue'
import { DOMESTIC_PROVINCES, OVERSEAS_GROUPS, NOT_LISTED_REGION_VALUE } from '@/constants/regions'

const props = withDefaults(defineProps<{
  value?: string
  placeholder?: string
  /** 紧凑高度（32px，商机详情页 antd 表单行高）；默认 36px 对齐 /lead 自定义输入框 */
  dense?: boolean
}>(), {
  value: '',
  placeholder: '选择国家或地区',
  dense: false,
})

const emit = defineEmits<{ (e: 'update:value', v: string): void }>()

const open = ref(false)
/** null=顶层；'CN'=国内省级；'OS'=海外大洲列表；其他值=大洲名（该大洲国家 chips） */
const drill = ref<null | 'CN' | 'OS' | string>(null)

watch(open, (v) => { if (!v) drill.value = null })

function pick(v: string) {
  emit('update:value', v)
  open.value = false
  drill.value = null
}
</script>

<template>
  <a-popover v-model:open="open" trigger="click" placement="bottomLeft" :arrow="false" overlay-class-name="drs-overlay">
    <button type="button" class="drs-trigger" :class="{ dense: props.dense, open }">
      <span :class="props.value ? 'has-value' : 'is-placeholder'">{{ props.value || props.placeholder }}</span>
      <DownOutlined class="drs-caret" />
    </button>
    <template #content>
      <div class="drs-panel">
        <template v-if="!drill">
          <button type="button" class="drs-row" @click="drill = 'CN'">
            <span>国内</span><span class="drs-desc">省级行政区</span>
          </button>
          <button type="button" class="drs-row" @click="drill = 'OS'">
            <span>海外</span><span class="drs-desc">按国家/地区</span>
          </button>
          <button type="button" class="drs-row" @click="pick(NOT_LISTED_REGION_VALUE)">
            <span>不在列表中</span><span class="drs-desc">名单外地区</span>
          </button>
        </template>
        <template v-else-if="drill === 'CN'">
          <button type="button" class="drs-back" @click="drill = null">‹ 国内</button>
          <div class="drs-chips">
            <button
              v-for="p in DOMESTIC_PROVINCES"
              :key="p"
              type="button"
              class="drs-chip"
              :class="{ active: props.value === `国内-${p}` }"
              @click="pick(`国内-${p}`)"
            >{{ p }}</button>
          </div>
        </template>
        <template v-else-if="drill === 'OS'">
          <button type="button" class="drs-back" @click="drill = null">‹ 海外</button>
          <div class="drs-chips">
            <button
              v-for="g in OVERSEAS_GROUPS"
              :key="g.continent"
              type="button"
              class="drs-chip"
              @click="drill = g.continent"
            >{{ g.continent }}</button>
          </div>
        </template>
        <template v-else>
          <button type="button" class="drs-back" @click="drill = 'OS'">‹ {{ drill }}</button>
          <div class="drs-chips">
            <button
              v-for="c in (OVERSEAS_GROUPS.find((g) => g.continent === drill)?.countries || [])"
              :key="c"
              type="button"
              class="drs-chip"
              :class="{ active: props.value === `海外-${c}` }"
              @click="pick(`海外-${c}`)"
            >{{ c }}</button>
          </div>
        </template>
      </div>
    </template>
  </a-popover>
</template>

<style scoped>
.drs-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 36px;
  padding: 0 12px;
  font-size: var(--cpq-font-size-base);
  font-family: inherit;
  text-align: left;
  color: var(--cpq-text-primary);
  background: var(--cpq-glass-2-bg);
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-sm);
  cursor: pointer;
}
.drs-trigger.dense { height: 32px; padding: 0 11px; }
.drs-trigger.open { border-color: var(--cpq-accent-primary); }
.drs-trigger .is-placeholder { color: var(--cpq-text-muted); }
.drs-caret { font-size: 10px; color: var(--cpq-text-muted); }
.drs-trigger.open .drs-caret { transform: rotate(180deg); }
.drs-panel { width: 320px; max-width: calc(100vw - 32px); }
.drs-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: var(--cpq-radius-sm);
  background: transparent;
  color: var(--cpq-text-primary);
  font-size: var(--cpq-font-size-sm);
  text-align: left;
  cursor: pointer;
}
.drs-row:hover { background: var(--cpq-overlay-a5); }
.drs-row + .drs-row { margin-top: 2px; }
.drs-desc { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.drs-back {
  padding: 0;
  margin-bottom: 8px;
  border: none;
  background: transparent;
  color: var(--cpq-accent-primary);
  font-size: var(--cpq-font-size-sm);
  cursor: pointer;
}
.drs-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.drs-chip {
  padding: 4px 10px;
  border: 1px solid var(--cpq-border-primary);
  border-radius: var(--cpq-radius-full);
  background: var(--cpq-overlay-a5);
  color: var(--cpq-text-secondary);
  font-size: var(--cpq-font-size-sm);
  cursor: pointer;
}
.drs-chip:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
.drs-chip.active { border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); color: var(--cpq-accent-primary); }
</style>
