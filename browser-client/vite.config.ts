import { defineConfig } from 'vite';

export default defineConfig({
    server: {
        host: '127.0.0.1',
        port: 5173,
        strictPort: true,
        proxy: {
            '/session': { target: 'http://127.0.0.1:8090', ws: true },
            '/api': { target: 'http://127.0.0.1:8090' },
        },
    },
    build: { target: 'es2022', sourcemap: true },
});
