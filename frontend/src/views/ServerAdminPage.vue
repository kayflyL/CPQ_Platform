<script setup lang="ts">
/** 服务器管理后台（/servers/admin）— 产品系列 / 机型管理 / 基准配置 / 料号库 六 tab。
 *  从配置门户 /servers 拆出：配置=面向客户的展示，管理=内部维护。
 *  配件适配 tab 已移除（2026-08-03）：specs.chassis 声明未被任何装配逻辑消费，纯参考视图 → 删除。 */
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import SeriesManager from '@/components/server-admin/SeriesManager.vue'
import PartsLibrary from '@/components/server-admin/PartsLibrary.vue'
import BaseConfigBuilder from '@/components/server-admin/BaseConfigBuilder.vue'
import BomTemplateManager from '@/components/server-admin/BomTemplateManager.vue'
import ModelManager from '@/components/server-admin/ModelManager.vue'
import ServerDrawingPortal from '@/components/server-admin/ServerDrawingPortal.vue'
import PortalBannerSettings from '@/components/server-admin/PortalBannerSettings.vue'

const route = useRoute()
const adminTab = ref<'models' | 'series' | 'base' | 'parts' | 'drawing' | 'portal'>('models')

/** Tab 注册表 —— 分段导航与面板挂载共用 */
const TABS = [
  { key: 'models',  label: '机型管理' },
  { key: 'series',  label: '产品系列' },
  { key: 'base',    label: '基准配置' },
  { key: 'parts',   label: '料号库' },
  { key: 'drawing', label: '图纸配置' },
  { key: 'portal',  label: '门户设置' },
] as const

/** 子页返回/外链入口切 tab：图纸编辑器返回用 ?tab=drawing；机型/基准编辑器保存后带 ?refresh= 回来。 */
watch(() => [route.query.tab, route.query.refresh], ([tab, refresh]) => {
  const t = tab || refresh
  if (t === 'models') adminTab.value = 'models'
  else if (t === 'drawing') adminTab.value = 'drawing'
  else if (t === 'base-config') adminTab.value = 'base'
}, { immediate: true })

const adminLayout = ref<HTMLElement | null>(null)
/** 切区滚动归顶 —— v-show 七区共用滚动容器，不归顶会残留上一区滚动深度（短区被钳位、回切跳回深处） */
watch(adminTab, () => {
  const sc = adminLayout.value?.closest('.main-scroll') as HTMLElement | null
  sc?.scrollTo({ top: 0 })
})
</script>

<template>
  <div class="server-admin-page">
    <div class="page-inner">
      <div class="admin-layout" ref="adminLayout">
        <aside class="admin-rail">
          <div class="rail-brand">CPQ · 服务器管理</div>
          <button v-for="t in TABS" :key="t.key" type="button" class="rail-item" :class="{ active: adminTab === t.key }" @click="adminTab = t.key">{{ t.label }}</button>
        </aside>
        <main class="admin-content">
          <ModelManager v-show="adminTab === 'models'" />
          <SeriesManager v-show="adminTab === 'series'" />
          <BaseConfigBuilder v-show="adminTab === 'base'" />
          <BomTemplateManager v-show="adminTab === 'base'" />
          <PartsLibrary v-show="adminTab === 'parts'" />
          <ServerDrawingPortal v-show="adminTab === 'drawing'" />
          <PortalBannerSettings v-show="adminTab === 'portal'" />
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.server-admin-page { padding: 4px 0 80px; }
.page-inner { max-width: 1180px; margin: 0 auto; padding: 0 24px; }
.admin-layout { display: flex; }
/* 左栏配方与解决方案页（StrategyPortal.side）同款 */
.admin-rail {
  width: 216px; flex-shrink: 0; padding: 14px 12px;
  border-right: 1px solid var(--cpq-glass-border);
  position: sticky; top: var(--cpq-sticky-top, 0px);
  max-height: calc(100vh - var(--cpq-sticky-top, 0px));
  overflow: auto;
  align-self: flex-start;
}
.rail-brand { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 10.5px; letter-spacing: .18em; color: var(--cpq-text-muted); padding: 0 10px 16px; }
.rail-item {
  display: flex; align-items: center; width: 100%; padding: 8px 10px; margin-bottom: 2px;
  border: none; border-radius: var(--cpq-radius-sm); background: none; color: var(--cpq-text-secondary);
  font-size: 13.5px; text-align: left; cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.rail-item:hover { background: var(--cpq-overlay-w6); color: var(--cpq-text-primary); }
.rail-item.active {
  background: color-mix(in srgb, var(--cpq-accent-primary) 12%, transparent);
  color: var(--cpq-text-primary); font-weight: 600;
}
.admin-content { flex: 1; min-width: 0; padding: 14px 4px 60px 26px; }
@media (max-width: 768px) {
  .page-inner { padding: 0 12px; }
  .admin-layout { display: block; }
  .admin-rail {
    position: static; width: 100%; height: auto;
    display: flex; gap: 4px; overflow-x: auto;
    border-right: none; border-bottom: 1px solid var(--cpq-glass-border);
    margin-bottom: 14px; padding: 0 0 8px;
  }
  .rail-brand { display: none; }
  .rail-item { white-space: nowrap; flex: 1 0 auto; margin-bottom: 0; }
}
</style>
