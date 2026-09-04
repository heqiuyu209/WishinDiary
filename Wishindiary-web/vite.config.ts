import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          // 将 ECharts 独立拆包，避免阻塞主脚本加载
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) {
            return 'echarts';
          }
          // 将 Vue 生态核心依赖拆包
          if (
            id.includes('node_modules/vue') ||
            id.includes('node_modules/vue-router') ||
            id.includes('node_modules/pinia') ||
            id.includes('node_modules/axios')
          ) {
            return 'vendor';
          }
          // 将 v-calendar 独立拆包
          if (id.includes('node_modules/v-calendar') || id.includes('node_modules/date-fns')) {
            return 'calendar';
          }
        },
      },
    },
  },
});
