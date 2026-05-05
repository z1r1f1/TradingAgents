import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      globals: {
        document: 'readonly', localStorage: 'readonly', fetch: 'readonly', Error: 'readonly',
        String: 'readonly', Boolean: 'readonly', Number: 'readonly', Date: 'readonly', console: 'readonly',
        HTMLButtonElement: 'readonly', RequestInit: 'readonly', FormEvent: 'readonly'
      }
    },
    rules: { '@typescript-eslint/no-explicit-any': 'off' }
  }
];
