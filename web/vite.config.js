import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// study-liu Web 前端构建配置
// 开发期把 /api 反向代理到 Python 后端（server/api_server.py，默认 8000 端口），
// 这样前端不需要处理跨域，生产环境也可以把 dist/ 交给任意静态服务器托管。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        // SSE 必须关闭缓冲，否则事件会被攒着一起发，看不到“链路推进”的过程
        ws: false,
        configure(proxy) {
          proxy.on('proxyRes', (proxyRes) => {
            if (String(proxyRes.headers['content-type'] || '').includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            }
          })
        },
      },
    },
  },
})
