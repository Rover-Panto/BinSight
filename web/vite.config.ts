import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'

const localServerControl = (): Plugin => ({
  name: 'binsight-local-server-control',
  apply: 'serve',
  configureServer(server) {
    server.middlewares.use('/__binsight/stop', (request, response, next) => {
      if (request.method !== 'POST') {
        next()
        return
      }

      const remoteAddress = request.socket.remoteAddress ?? ''
      const isLocal = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(remoteAddress)
      const validControlRequest = request.headers['x-binsight-control'] === 'stop'
      if (!isLocal || !validControlRequest) {
        response.statusCode = 403
        response.end(JSON.stringify({ ok: false }))
        return
      }

      response.statusCode = 200
      response.setHeader('Content-Type', 'application/json')
      response.end(JSON.stringify({ ok: true }))

      setTimeout(() => {
        void server.close().finally(() => process.exit(0))
      }, 450)
    })
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), localServerControl()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    include: ['src/**/*.test.{ts,tsx}'],
    pool: 'forks',
    maxWorkers: 1,
    fileParallelism: false,
  },
})
