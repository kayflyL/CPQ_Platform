<script setup lang="ts">
/** 服务器配置门户（/servers）— 面向销售/客户的产品入口。
 *  选服务器类型 → 跳机型目录 → 看产品详情 → 配置。
 *  管理后台已拆到 /servers/admin（ServerAdminPage）。 */
import ModelCatalog from '@/components/server-config/ModelCatalog.vue'
</script>

<template>
  <div class="server-page">
    <div class="page-inner">
      <ModelCatalog />
    </div>
  </div>
</template>

<style scoped>
.server-page { padding: 4px 0 80px; }
.page-inner { max-width: 1180px; margin: 0 auto; padding: 0 24px; }
</style>
