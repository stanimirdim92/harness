import react from '@vitejs/plugin-react';
import path from 'node:path';
import { configDefaults, defineConfig } from 'vitest/config';
import svgr from 'vite-plugin-svgr';

const claudeToolingDirectory = `${path.resolve(__dirname, '.claude')}/**`;

export default defineConfig({
    plugins: [
        react(),
        svgr({
            include: ['**/*.svg?react'],
        }),
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, 'resources/js'),
        },
    },
    test: {
        exclude: [...configDefaults.exclude, '.claude/**', 'vendor/**'],
        environment: 'jsdom',
        globals: true,
        // Several agent sessions run tests at once; one worker per CPU exhausts RAM.
        maxWorkers: 4,
        setupFiles: ['./resources/js/test/setup.ts'],
        coverage: {
            provider: 'v8',
            include: ['resources/js/**/*.{js,jsx,ts,tsx}'],
            exclude: [
                claudeToolingDirectory,
                '**/*.d.ts',
                '**/*.{test,spec}.{js,jsx,ts,tsx}',
                '**/__tests__/**',
                'resources/js/test/**',
            ],
            reportsDirectory: './test-results/coverage/frontend',
            reporter: [
                'text-summary',
                ['text-summary', { file: 'summary.txt' }],
                'html',
                'lcovonly',
                'json-summary',
            ],
            reportOnFailure: true,
        },
    },
});
