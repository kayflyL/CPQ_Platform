<script setup lang="ts">
/** 公开目录页宿主 —— ModelCatalog 组件的公开模式包装（10 行薄壳，数据源公开 API）。 */
import ModelCatalog from '@/components/server-config/ModelCatalog.vue'
</script>

<template>
  <ModelCatalog public-mode />
</template>
