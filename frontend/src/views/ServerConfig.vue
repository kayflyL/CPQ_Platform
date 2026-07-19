<script setup lang="ts">
/** 服务器页（/servers）— 配置/管理双模式入口。
 *  配置模式：选服务器类型 → 跳转机型目录页
 *  管理模式：tab 切换料号库 / 基准配置 */
import { ref } from 'vue'
import ModelCatalog from '@/components/server-config/ModelCatalog.vue'
import PartsLibrary from '@/components/server-admin/PartsLibrary.vue'
import BaseConfigBuilder from '@/components/server-admin/BaseConfigBuilder.vue'
import BomTemplateManager from '@/components/server-admin/BomTemplateManager.vue'
import ModelManager from '@/components/server-admin/ModelManager.vue'

const mode = ref<'config' | 'admin'>('config')
const adminTab = ref<'parts' | 'base' | 'models'>('parts')
</script>

<template>
  <div class="server-page">
    <div class="page-inner">
      <div class="mode-tabs">
        <a-radio-group v-model:value="mode" button-style="solid" size="small">
          <a-radio-button value="config">配置</a-radio-button>
          <a-radio-button value="admin">管理</a-radio-button>
        </a-radio-group>
        <span class="mode-hint">{{ mode === 'config' ? '选机型、配机箱' : '维护料号库、组装基准配置' }}</span>
      </div>

      <ModelCatalog v-show="mode === 'config'" />
      <div v-show="mode === 'admin'" class="admin-wrap">
        <a-radio-group v-model:value="adminTab" button-style="solid" size="small" class="admin-tabs">
          <a-radio-button value="parts">料号库</a-radio-button>
          <a-radio-button value="base">基准配置</a-radio-button>
          <a-radio-button value="models">机型管理</a-radio-button>
        </a-radio-group>
        <PartsLibrary v-show="adminTab === 'parts'" />
        <BaseConfigBuilder v-show="adminTab === 'base'" />
        <BomTemplateManager v-show="adminTab === 'base'" />
        <ModelManager v-show="adminTab === 'models'" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.server-page {
  padding: 4px 0 80px;
}
.page-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 24px;
}
.mode-tabs {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}
.mode-hint {
  color: var(--cpq-text-muted, #6E7582);
  font-size: 12px;
}
.admin-wrap {
  max-width: 1100px;
}
.admin-tabs {
  margin-bottom: 14px;
}
</style>
