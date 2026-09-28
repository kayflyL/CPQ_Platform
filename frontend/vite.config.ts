import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    Components({
      resolvers: [AntDesignVueResolver({ importStyle: false })],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  optimizeDeps: {
    include: [
      'exceljs',
      'three',
      'pixi.js',
      'echarts',
      'vue-echarts',
      '@univerjs/core',
      '@univerjs/preset-sheets-core',
      'ant-design-vue',
      '@vue-flow/core',
      '@vue-flow/background',
      '@vue-flow/controls',
      '@vue-flow/minimap',
    ],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          const normalized = id.replace(/\\/g, '/')
          if (normalized.includes('node_modules/exceljs')) return 'exceljs'
          if (normalized.includes('node_modules/three')) return 'three'
          if (normalized.includes('node_modules/pixi.js')) return 'pixi'
          if (normalized.includes('node_modules/echarts')) return 'echarts'
          if (normalized.includes('node_modules/@univerjs')) return 'univer'
          if (normalized.includes('node_modules/ant-design-vue')) return 'antd'
          if (normalized.includes('@vue-flow')) return 'vueflow'
          return undefined
        },
      },
    },
  },
  server: {
    host: true, // 局域网可访问：监听 0.0.0.0（别人通过 http://<本机IP>:5173 打开）
    port: Number(process.env.PORT) || 5173,
    proxy: {
      '/api': {
        // 默认本机 8000；多后端并行时可用 VITE_API_TARGET 覆盖（如临时验证后端 8010）
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
    warmup: {
      clientFiles: [
        'src/views/portal/Portal.vue',
        'src/views/office/AiOfficeView.vue',
        'src/views/opportunity/OpportunityList.vue',
        'src/views/ServerConfig.vue',
        'src/views/admin/Parts.vue',
        'src/views/admin/StrategyPortal.vue',
        'src/views/ExcelParser.vue',
        'src/views/export-templates/ExportTemplateList.vue',
        'src/views/admin/UserRoleManagement.vue',
        'src/views/ServerAdminPage.vue',
      ],
    },
  },
})
