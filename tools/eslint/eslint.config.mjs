// ESLint configuration used ONLY to analyse code submitted for review.
// It is deliberately independent of the frontend's own lint config: reviewed
// code must be judged against a fixed ruleset, not against whatever config the
// submitter happens to ship.
import js from '@eslint/js';
import security from 'eslint-plugin-security';
import tseslint from 'typescript-eslint';

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  security.configs.recommended,
  {
    files: ['**/*.{js,mjs,cjs,jsx,ts,mts,cts,tsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      // Security rules the reviewer cares most about.
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-script-url': 'error',
      eqeqeq: ['warn', 'always'],

      // Submitted code is a fragment, not a project: these would only produce
      // noise about imports and globals we cannot resolve.
      'no-undef': 'off',
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-require-imports': 'off',
      'no-unused-vars': 'off',
    },
  },
];
