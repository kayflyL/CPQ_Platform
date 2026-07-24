<script setup lang="ts">
/** 服务器管理后台（/servers/admin）— 机型管理 / 基准配置 / 料号库 三 tab。
 *  从配置门户 /servers 拆出：配置=面向客户的展示，管理=内部维护。 */
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PartsLibrary from '@/components/server-admin/PartsLibrary.vue'
import BaseConfigBuilder from '@/components/server-admin/BaseConfigBuilder.vue'
import BomTemplateManager from '@/components/server-admin/BomTemplateManager.vue'
import ModelManager from '@/components/server-admin/ModelManager.vue'

const route = useRoute()
const adminTab = ref<'models' | 'base' | 'parts'>('models')

/** 子页（机型/基准编辑器）保存后带 ?refresh= 回来，切到对应 tab。 */
watch(() => route.query.refresh, (v) => {
  if (v === 'models') adminTab.value = 'models'
  else if (v === 'base-config') adminTab.value = 'base'
}, { immediate: true })
</script>

<template>
  <div class="server-admin-page">
    <div class="page-inner">
      <a-radio-group v-model:value="adminTab" button-style="solid" size="small" class="admin-tabs">
        <a-radio-button value="models">机型管理</a-radio-button>
        <a-radio-button value="base">基准配置</a-radio-button>
        <a-radio-button value="parts">料号库</a-radio-button>
      </a-radio-group>
      <ModelManager v-show="adminTab === 'models'" />
      <BaseConfigBuilder v-show="adminTab === 'base'" />
      <BomTemplateManager v-show="adminTab === 'base'" />
      <PartsLibrary v-show="adminTab === 'parts'" />
    </div>
  </div>
</template>

<style scoped>
.server-admin-page { padding: 4px 0 80px; }
.page-inner { max-width: 1100px; margin: 0 auto; padding: 0 24px; }
.admin-tabs { margin-bottom: 14px; }
</style>
