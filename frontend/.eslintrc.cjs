/**
 * .eslintrc.cjs — Reglas de linting del frontend.
 *
 * El proyecto declaraba las dependencias de ESLint y el script `npm run lint`,
 * pero no existía este archivo: el comando fallaba y ningún push pasaba nunca
 * por el linter. Esta configuración lo pone en marcha con el conjunto de
 * reglas que corresponde al stack (TypeScript + React + hooks).
 *
 * Criterio: reglas que atrapan errores reales van como `error`; las de estilo
 * puro se dejan fuera (el formateo no debe romper CI).
 */
module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['@typescript-eslint', 'react-refresh'],
  ignorePatterns: [
    'dist',
    'node_modules',
    'public',
    '*.config.js',
    '*.config.ts',
    '.eslintrc.cjs',
  ],
  rules: {
    // Desactivada a propósito: el proyecto sigue el patrón idiomático de
    // colocar cada contexto junto a su hook de acceso (useTheme, Toast,
    // ToastProvider…). Esa colocación es deliberada y hace que la regla
    // dispare en ~15 archivos sanos; el coste sería solo de Fast Refresh en
    // desarrollo, no un defecto de producción.
    'react-refresh/only-export-components': 'off',

    // `any` deshace la garantía de tipos que justifica usar TypeScript, pero
    // hay puntos de integración (respuestas de API de terceros) donde es
    // pragmático: aviso, no error.
    '@typescript-eslint/no-explicit-any': 'warn',

    // Variables sin usar: error, salvo el convenio de prefijo `_` para
    // parámetros que la firma exige pero el cuerpo no necesita.
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
    ],
    'no-unused-vars': 'off', // La sustituye la regla de @typescript-eslint

    // Errores reales que TypeScript no cubre por sí solo.
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    eqeqeq: ['error', 'always', { null: 'ignore' }],
    'no-var': 'error',
    'prefer-const': 'error',
  },
  overrides: [
    {
      // En los tests, `any` y los console son herramientas legítimas de
      // diagnóstico y no deben bloquear la suite.
      files: ['**/*.test.ts', '**/*.test.tsx', 'src/test/**'],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
        'no-console': 'off',
      },
    },
  ],
}
