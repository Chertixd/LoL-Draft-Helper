import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';

export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            '@': resolve(__dirname, './src'),
            '@counterpick/core': resolve(__dirname, '../../packages/core/src')
        }
    },
    server: {
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://localhost:5000',
                changeOrigin: true
            }
        }
    },
    define: {
        APP_VERSION: JSON.stringify(process.env.npm_package_version)
    },
    build: {
        target: 'esnext'
    },
    esbuild: {
        pure: process.env.NODE_ENV === 'production'
            ? ['console.log', 'console.debug', 'console.info']
            : []
    }
});

