import coreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

/**
 * ESLint flat config.
 *
 * Next 16 removed the `next lint` command, so `npm run lint` invoked a
 * subcommand that no longer exists and always exited 1. `eslint` and
 * `eslint-config-next` were already devDependencies; only this config file was
 * missing, so nothing new is installed.
 *
 * `eslint-config-next` v16 ships flat configs directly — they are spread here
 * rather than wrapped in FlatCompat, which is for the legacy `.eslintrc` shape.
 */
const config = [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'next-env.d.ts',
      'playwright-report/**',
      'test-results/**',
      '.playwright/**',
    ],
  },
  ...coreWebVitals,
  ...nextTypescript,
  {
    // End-to-end specs are Node programs that drive a browser; no React runs
    // in them. The hooks rule in particular misreads Playwright's fixture
    // callback — its parameter is conventionally named `use`, which the rule
    // sees as React's `use` hook being called outside a component.
    files: ['e2e/**/*.ts', 'playwright.config.ts'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
    },
  },
];

export default config;
