import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // `catch (e)` / `catch (_)` with the error deliberately ignored is the
      // house style for best-effort localStorage and fetch calls.
      'no-unused-vars': ['error', {
        varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^_', caughtErrors: 'none',
      }],
      // Contexts and modals export a hook or a constant next to the component.
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
      // **Esta regra existe por um painel que abriu em PRETO** (17-set-2026).
      // O `AuthContext` usava uma `const` (`pegarMediaToken`) 45 linhas acima
      // da declaracao dela, no array de dependencias de um `useEffect` -- que o
      // React avalia durante o RENDER. A `const` ainda estava na zona morta
      // temporal, entao o `AuthProvider`, que embrulha o app inteiro, morria com
      // `ReferenceError: Cannot access ... before initialization`. O `#root`
      // ficava vazio: sem tela, sem mensagem, sem log no servidor.
      //
      // O `npm run build` NAO pega -- o import resolve e a sintaxe esta certa --,
      // entao o CI passou verde com o painel quebrado. Esta regra pega, e e por
      // isso que ela entra como `error` e nao como aviso.
      //
      // `functions: false` porque declaracao de funcao sobe (hoisting) e usa-la
      // antes e idioma normal de JS; o que estoura e `const`/`let`/`class`.
      'no-use-before-define': ['error', {
        functions: false, classes: true, variables: true, allowNamedExports: false,
      }],
    },
  },
  {
    // The entry point mounts a few one-off components; nothing here hot-reloads.
    files: ['src/main.jsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    files: ['vite.config.js', 'vite-plugin-seo.js', 'seo/**/*.js'],
    languageOptions: { globals: { ...globals.node } },
  },
])
