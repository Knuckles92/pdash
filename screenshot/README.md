# pdash screenshot sidecar

Headless-Chromium service that renders a URL to a PNG. The pdash **backend**
calls `POST /capture` (agents never call it directly) when an agent uses the
`screenshot_page` MCP tool.

## Why it exists

A real screenshot of a dashboard needs the actual React app rendered in a
browser — Recharts, Tailwind theming, and the responsive grid only exist at
runtime. Chromium is a ~300-400MB dependency, so it lives here instead of in the
lean backend image. The service runs only on the internal docker network with
no published ports.

## API

`POST /capture`

```json
{
  "url": "http://frontend:3000/pages/ops",
  "cookies": [{"name": "session", "value": "<signed>", "url": "http://frontend:3000"}],
  "viewport_width": 1280,
  "viewport_height": 1024,
  "full_page": true,
  "wait_ms": 600
}
```

Returns `image/png`. The backend mints the `session` cookie (a short-lived admin
session) so the captured page is the authenticated dashboard — there is one
admin, so an agent's screenshot shows what the admin sees.

`GET /healthz` → `{"status": "ok"}`.

## Auth

`/capture` requires `Authorization: Bearer <PDASH_SERVICE_SECRET>` — the same
secret the backend↔MCP hop uses. It **fails closed**: if `PDASH_SERVICE_SECRET`
is unset, `/capture` returns `503` until you set it. To deliberately run without
auth on a fully-trusted, isolated network, set `PDASH_SCREENSHOT_ALLOW_NO_AUTH=1`
(a loud warning is logged at startup). Note `/capture` takes an arbitrary `url`
and `cookies`, so an unauthenticated instance is an in-network rendering proxy —
keep it authenticated.

## Config (env)

| Var | Default | Meaning |
|---|---|---|
| `PDASH_SERVICE_SECRET` | — | Required Bearer token; unset ⇒ /capture refused (503). |
| `PDASH_SCREENSHOT_ALLOW_NO_AUTH` | — | Set to `1` to allow unauthenticated /capture. |
| `PDASH_SCREENSHOT_NAV_TIMEOUT_MS` | `20000` | Navigation timeout. |
| `PDASH_SCREENSHOT_MAX_HEIGHT_PX` | `8000` | Clamp full-page capture height (clips taller pages). |

## Local run

```bash
pip install . && playwright install --with-deps chromium
uvicorn app.main:app --host 0.0.0.0 --port 9000
```
