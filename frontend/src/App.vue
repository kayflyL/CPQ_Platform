<template>
  <a-config-provider 
    :theme="themeConfig"
    :getPopupContainer="getPopupContainer"
  >
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
const getPopupContainer = () => document.getElementById('app') || document.body

const themeConfig = {
  token: {
    colorPrimary: '#00F5D4',
    colorBgBase: '#08090B',
    colorBgContainer: '#101217',
    colorTextBase: '#E8ECEF',
    colorTextSecondary: '#8A9099',
    colorBorder: 'rgba(255,255,255,0.10)',
    // Tooltip 组件 token
    colorBgSpotlight: '#171a21', // 深色背景
    colorTextLightSolid: '#E8ECEF', // 白色文字
  },
}
</script>