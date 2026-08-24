<script setup lang="ts">
/** 服务器配置门户（/servers）— 面向销售/客户的产品入口。
 *  banner 全幅由 ModelCatalog 自管（旭日舞台 + 类型胶囊 + 机型货架）。
 *  管理后台已拆到 /servers/admin（ServerAdminPage）。 */
import ModelCatalog from '@/components/server-config/ModelCatalog.vue'
</script>

<template>
  <ModelCatalog />
</template>
