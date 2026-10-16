import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  // ── Build optimisation for mobile & slow networks ──
  build: {
    target: 'es2020',
    // Split vendor chunks: React + router stay in main bundle (<200KB)
    // Large libraries split into async chunks for mobile-friendly loading
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          // Vendor: React ecosystem (core, router, etc.)
          if (id.includes('node_modules/react') ||
              id.includes('node_modules/react-dom') ||
              id.includes('node_modules/react-router') ||
              id.includes('node_modules/scheduler')) {
            return 'vendor-react';
          }
          // Vendor: UI primitives (icons, animation, etc.)
          if (id.includes('node_modules/lucide-react') ||
              id.includes('node_modules/framer-motion')) {
            return 'vendor-ui';
          }
          // Vendor: Everything else from node_modules
          if (id.includes('node_modules')) {
            return 'vendor-libs';
          }
          // App code: Vite auto-splits by dynamic import() boundaries
        },
      },
    },
    // Mobile-friendly: warn above 400KB per chunk
    chunkSizeWarningLimit: 400,
  },

  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icon-192.png', 'icon-512.png', 'icon-512-maskable.png'],
      manifest: {
        name: '问津 · AI社会调查工作台',
        short_name: '问津',
        description: 'AI驱动的社会科学调查工具箱 — 选题、问卷、田野、分析、成果库',
        theme_color: '#1E3A8A',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/?utm_source=pwa',
        scope: '/',
        id: '/?app=wenjin',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
        ],
        categories: ['productivity', 'education'],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        skipWaiting: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            // Never cache survey, transcript, auth, or provider responses.
            urlPattern: /\/api\/.*/i,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
})
