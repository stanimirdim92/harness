import './eslint.compat.js';

import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import importPlugin from 'eslint-plugin-import';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import unusedImports from 'eslint-plugin-unused-imports';
import tseslint from 'typescript-eslint';

export default [
    js.configs.recommended,

    ...tseslint.configs.recommended,
    ...tseslint.configs.recommendedTypeChecked,

    {
        files: ['resources/js/**/*.{js,jsx,ts,tsx}'],
        languageOptions: {
            parserOptions: {
                project: ['./tsconfig.json'],
                tsconfigRootDir: import.meta.dirname,
            },
        },
        plugins: {
            react,
            'react-hooks': reactHooks,
            'react-refresh': reactRefresh,
            import: importPlugin,
            'jsx-a11y': jsxA11y,
            'unused-imports': unusedImports,
        },
        settings: {
            react: { version: 'detect' },
            'import/resolver': {
                typescript: { project: './tsconfig.json' },
            },
        },
        rules: {
            'react/react-in-jsx-scope': 'off',
            'react/prop-types': 'off',

            'react/no-unescaped-entities': 'warn',

            ...reactHooks.configs.recommended.rules,

            'react-hooks/preserve-manual-memoization': 'warn',
            'react-hooks/purity': 'warn',
            'react-hooks/incompatible-library': 'off',
            'react-hooks/static-components': 'warn',
            'react-hooks/set-state-in-effect': 'warn',

            '@typescript-eslint/no-empty-object-type': 'warn',

            'react-refresh/only-export-components': 'warn',

            'unused-imports/no-unused-imports': 'error',
            'unused-imports/no-unused-vars': [
                'warn',
                {
                    vars: 'all',
                    varsIgnorePattern: '^_',
                    args: 'after-used',
                    argsIgnorePattern: '^_',
                },
            ],
            '@typescript-eslint/no-unused-vars': 'off',

            'import/order': [
                'error',
                {
                    groups: [
                        'builtin',
                        'external',
                        'internal',
                        'parent',
                        'sibling',
                        'index',
                        'object',
                        'type',
                    ],
                    'newlines-between': 'always',
                    alphabetize: { order: 'asc', caseInsensitive: true },
                },
            ],

            '@typescript-eslint/consistent-type-imports': [
                'warn',
                { prefer: 'type-imports' },
            ],

            '@typescript-eslint/no-floating-promises': 'warn',
            '@typescript-eslint/no-misused-promises': 'warn',
            '@typescript-eslint/no-base-to-string': 'warn',
            '@typescript-eslint/no-redundant-type-constituents': 'warn',

            '@typescript-eslint/no-unsafe-assignment': 'warn',
            '@typescript-eslint/no-unsafe-argument': 'warn',
            '@typescript-eslint/no-unsafe-member-access': 'warn',
            '@typescript-eslint/no-unsafe-call': 'warn',
            '@typescript-eslint/no-unsafe-return': 'warn',

            '@typescript-eslint/no-explicit-any': 'warn',
            '@typescript-eslint/no-unnecessary-type-assertion': 'warn',

            'no-empty': ['warn', { allowEmptyCatch: true }],
            'no-unsafe-finally': 'warn',
            'no-shadow-restricted-names': 'warn',
            'no-var': 'warn',

            ...prettier.rules,
        },
    },

    {
        ignores: [
            'node_modules/**',
            'public/**',
            'dist/**',
            'build/**',
            'vendor/**',
        ],
    },
];