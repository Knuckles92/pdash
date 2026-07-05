# pdash frontend (Phase 2)

Next.js 15 App Router + Tailwind v4 admin UI for the pdash backend.

## What's in Phase 2

- Login at `/login` (single password → backend `POST /api/v1/auth/login`).
- Route protection via `middleware.ts` (redirects to `/login` when no `session` cookie).
- Sidebar (desktop, collapsible) + bottom tab bar (mobile) + Pages drawer.
- Home page at `/` plus `/pages/[slug]` for non-home pages.
- Renderers for the four cheap module types: `markdown`, `key_value`, `table`, `link_list`.
- Edit mode (`?edit=1`): dnd-kit drag/reorder + Add/Edit module sheet driven by `/api/v1/module-schemas/{type}`.
- Settings: `/settings/agents` (register, rotate, enable/disable, revoke; plaintext key shown once) and `/settings/pages` (CRUD).
- Toasts via `sonner`, dark mode via `data-theme` (system / light / dark toggle).
- API client at `lib/api.ts` with same-origin cookies + `X-CSRF-Token` auto-injection + RFC 7807 `ApiError`.
- `<RealtimeProvider>` stub — real SSE arrives in Phase 5.

## Quick start

From the **repo root**:

```bash
cp .env.development.example .env
make setup
make dev
```

Open <http://localhost:3000> (default password `dev`). See [docs/dev.md](../docs/dev.md).

Frontend-only (with backend already on `:8080`):

```bash
cd frontend
npm run dev
```

## Configuration

- `PDASH_BACKEND_URL` (default `http://localhost:8080`) — where Next.js
  proxies `/api/*` requests. Same-origin cookies "just work" because the
  proxy is in front of the backend.
- `NEXT_PUBLIC_API_URL` — only set this if you want the client to bypass the
  Next.js rewrite and hit the backend cross-origin. In that case you must
  also add `PDASH_CORS_ORIGINS='["http://localhost:3000"]'` to the backend.

## Scripts

| Script           | Purpose                            |
|------------------|------------------------------------|
| `npm run dev`    | Dev server on :3000                |
| `npm run build`  | Production build                   |
| `npm run start`  | Run the production build           |
| `npm run lint`   | ESLint (next/core-web-vitals)      |
| `npm run typecheck` | tsc --noEmit                    |

## Stubs / deferred

- `<RealtimeProvider>` — does nothing in Phase 2 (`// TODO Phase 5`).
- `useApprovalCount()` — returns 0 (`// TODO Phase 3+5`).
- Table `action` cells render disabled with a "Phase 4" tooltip.
- `/approvals` and `/activity` are placeholder stubs (Phase 3 / 6).
- Remaining module types (`timeseries`, `log_stream`, `iframe`, `action_button`,
  `notification`) show a friendly fallback panel.
- `SchemaForm` is hand-rolled: covers the four phase-2 types' Pydantic-emitted
  JSON Schemas (object/array/string/number/boolean/enum, anyOf-with-null,
  $ref/allOf unwrapping). Swap to `@rjsf/core` later if schemas grow more
  exotic.

## Layout

See `tree -L 3 -I node_modules`.
