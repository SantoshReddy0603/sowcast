import tseslint from 'typescript-eslint';

export default tseslint.config(
  {ignores:['dist/**','node_modules/**','test-results/**']},
  ...tseslint.configs.recommended,
  {files:['**/*.js','**/*.mjs'],languageOptions:{globals:{process:'readonly',console:'readonly',
    window:'readonly',document:'readonly',innerWidth:'readonly',matchMedia:'readonly'}}},
  {files:['src/**/*.{ts,tsx}'], rules:{'no-debugger':'error',eqeqeq:'error',
    '@typescript-eslint/no-unused-vars':['error',{argsIgnorePattern:'^_'}]}},
);
