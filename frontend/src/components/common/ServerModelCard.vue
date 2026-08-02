<script setup lang="ts">
/** 机型卡片公共组件 — 统一机型管理/机型目录等场景的展示。
 *  可配置显示项：图片/生命周期/基准配置/规格/操作按钮。
 *  emit('click') 由父决定跳转逻辑（管理面不跳转，目录面跳详情页）。 */
import { computed } from 'vue'
import type { ServerModel } from '@/api/serverConfig'

type LifecycleStatus = 'new' | 'active' | 'eol' | 'discontinued'
const LIFECYCLES: { value: LifecycleStatus; label: string; chip: string }[] = [
  { value: 'new', label: '新品', chip: 'lc-new' },
  { value: 'active', label: '在售', chip: 'lc-active' },
  { value: 'eol', label: '即将停产', chip: 'lc-eol' },
  { value: 'discontinued', label: '停产', chip: 'lc-off' },
]
const lcMeta = (s?: string | null) => LIFECYCLES.find(l => l.value === s) || LIFECYCLES[1]

const props = withDefaults(defineProps<{
  model: ServerModel
  showImage?: boolean
  showLifecycle?: boolean
  showBaseConfig?: boolean
  showSpecs?: boolean
  showActions?: boolean
  clickable?: boolean
  typeName?: string
  baseConfigName?: string
  configCount?: number
}>(), {
  showImage: true,
  showLifecycle: true,
  showBaseConfig: true,
  showSpecs: true,
  showActions: false,
  clickable: true,
})

const emit = defineEmits<{
  (e: 'click'): void
  (e: 'edit'): void
  (e: 'delete'): void
}>()

const cardClass = computed(() => ({
  'model-card': true,
  'is-clickable': props.clickable,
}))
</script>

<template>
  <div :class="cardClass" @click="clickable && emit('click')">
    <!-- 生命周期角标 -->
    <span v-if="showLifecycle" class="lc-chip" :class="lcMeta(model.lifecycle_status).chip">
      {{ lcMeta(model.lifecycle_status).label }}
    </span>

    <!-- 机型图片 -->
    <div v-if="showImage" class="m-thumb">
      <img v-if="model.image_url" :src="model.image_url" :alt="model.name" />
      <span v-else class="m-thumb-ph">机</span>
    </div>

    <!-- 机型名 + 类型 -->
    <div class="m-name">{{ model.name }}</div>
    <div v-if="typeName" class="m-type">{{ typeName }}</div>

    <!-- 规格（形态/盘位/系列） -->
    <div v-if="showSpecs" class="m-specs">
      <span><i>形态</i>{{ model.base_config?.form || '—' }}</span>
      <span><i>盘位</i>{{ model.base_config?.bays ?? '—' }}</span>
      <span><i>系列</i>{{ model.base_config?.series || '—' }}</span>
    </div>

    <!-- 关联基准配置 -->
    <div v-if="showBaseConfig" class="m-bc">
      <template v-if="configCount != null">{{ configCount }} 个配置</template>
      <template v-else-if="baseConfigName">基准配置 · {{ baseConfigName }}</template>
      <template v-else>未关联基准配置</template>
    </div>

    <!-- 操作按钮（编辑/删除） -->
    <div v-if="showActions" class="m-foot">
      <a-button size="small" link @click.stop="emit('edit')">编辑</a-button>
      <a-popconfirm title="删除该机型？" @confirm="emit('delete')">
        <a-button size="small" link danger @click.stop>删除</a-button>
      </a-popconfirm>
    </div>
  </div>
</template>

<style scoped>
.model-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 14px;
  background: linear-gradient(135deg, var(--cpq-overlay-w6) 0%, var(--cpq-overlay-w3) 40%, var(--cpq-overlay-b20) 100%);
  backdrop-filter: blur(14px);
  box-shadow: 0 10px 30px var(--cpq-overlay-b20), inset 0 1px 0 var(--cpq-overlay-w15);
  transition: all .2s cubic-bezier(.16,1,.3,1);
}
.model-card.is-clickable {
  cursor: pointer;
}
.model-card.is-clickable:hover {
  border-color: var(--cpq-overlay-a30);
  transform: translateY(-2px);
  box-shadow: 0 16px 40px var(--cpq-shadow-color-strong), inset 0 1px 0 var(--cpq-overlay-w15);
}

.lc-chip {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
}
.lc-active { color: #1f9d6b; background: rgba(125, 215, 170, .18); border-color: rgba(125, 215, 170, .45); }
.lc-new    { color: #2f7de1; background: rgba(150, 195, 250, .18); border-color: rgba(150, 195, 250, .45); }
.lc-eol    { color: #c8861a; background: rgba(245, 200, 110, .18); border-color: rgba(245, 200, 110, .45); }
.lc-off    { color: var(--cpq-text-muted, #6E7582); background: var(--cpq-overlay-w6); border-color: var(--cpq-overlay-w15); }

.m-thumb {
  height: 92px;
  border-radius: 10px;
  overflow: hidden;
  background: var(--cpq-overlay-b20);
  border: 1px solid var(--cpq-overlay-w10);
  display: flex;
  align-items: center;
  justify-content: center;
}
.m-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.m-thumb-ph {
  font-size: 26px;
  font-weight: 700;
  color: var(--cpq-text-muted, #6E7582);
  opacity: .5;
}

.m-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--cpq-text-primary, #E8ECEF);
}
.m-type {
  font-size: 12px;
  color: var(--cpq-text-secondary, #9BA1AA);
}

.m-specs {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid var(--cpq-overlay-w10);
}
.m-specs span {
  display: flex;
  flex-direction: column;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary, #E8ECEF);
}
.m-specs i {
  font-size: 11px;
  font-weight: 400;
  font-style: normal;
  color: var(--cpq-text-muted, #6E7582);
}

.m-bc {
  font-size: 12px;
  color: var(--cpq-text-secondary, #9BA1AA);
}
.m-bc-empty {
  color: var(--cpq-text-muted, #6E7582);
  font-style: italic;
}

.m-foot {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 2px;
}
</style>