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
    include: ['exceljs'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          const normalized = id.replace(/\\/g, '/')
          if (normalized.includes('node_modules/exceljs')) return 'exceljs'
          if (normalized.includes('node_modules/three')) return 'three'
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
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
