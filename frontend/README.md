# AI-CRMS frontend

React 19 + Vite single-page app. See the [project README](../README.md) for setup.

```bash
npm ci
npm run dev        # http://localhost:5173 (expects the API on http://localhost:8000)
npm run lint
npm test           # unit + API-contract tests (node:test)
npm run test:e2e   # Playwright against a real API and throw-away database
npm run build
```

`VITE_API_URL` sets the API origin at build time; an empty value means "same origin" (used by the production nginx image, which proxies `/api`).

Structure: `src/services/api.js` (single HTTP client, cookie sessions, error helpers), `src/utils/` (formatting, vocabularies, paged-list hook), `src/components/ui.jsx` (accessible dialog, states, pagination), `src/pages/` (one lazily loaded module per route).
