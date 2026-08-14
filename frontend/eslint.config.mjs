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
    ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'],
  },
  ...coreWebVitals,
  ...nextTypescript,
];

export default config;
