<template>
  <a-config-provider
    :theme="themeConfig"
    :getPopupContainer="getPopupContainer"
  >
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { theme as antdTheme } from 'ant-design-vue'
import { useThemeStore } from '@/store/theme'

const getPopupContainer = () => document.getElementById('app') || document.body

const themeStore = useThemeStore()

// antd 关键 token 与 tokens.css 的 --cpq-* 显式对齐，保证 antd 组件与自定义组件视觉一致；
// algorithm 负责派生 hover/active 等中间色
const darkToken = {
  colorPrimary: '#1677FF',
  colorSuccess: '#52C9A0',
  colorError: '#FF6B6B',
  colorWarning: '#faad14',
  colorBgBase: '#08090B',
  colorBgContainer: '#101217',
  colorBgElevated: '#171a21',
  colorTextBase: '#E8ECEF',
  colorTextSecondary: '#9BA1AA',
  colorBorder: 'var(--cpq-overlay-w10)',
  colorBgSpotlight: '#171a21',
  colorTextLightSolid: '#E8ECEF',
}

const lightToken = {
  colorPrimary: '#1677FF',
  colorSuccess: '#52C9A0',
  colorError: '#FF6B6B',
  colorWarning: '#faad14',
  colorBgBase: '#ffffff',
  colorBgContainer: '#ffffff',
  colorBgElevated: '#ffffff',
  colorTextBase: '#1d2129',
  colorTextSecondary: '#4e5969',
  colorBorder: 'rgba(22, 119, 255, 0.10)',
  colorBgSpotlight: '#ffffff',
  // 主色实心面上的文字须用白(与 --cpq-accent-on-primary 对齐)；曾误对齐 colorTextBase 导致浅色下主按钮/实心 tab 蓝底深字
  colorTextLightSolid: '#ffffff',
}

const themeConfig = computed(() => ({
  algorithm: themeStore.isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  token: themeStore.isDark ? darkToken : lightToken,
}))
</script>
