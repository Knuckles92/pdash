# Agent-first MCP onboarding

How a brand-new AI client with **no API key** connects to pdash, asks to be
registered, and — after the admin approves — picks up its own `hb_agt_` key.

Every other MCP tool stays gated behind a valid agent key. Only three tools are
**ungated** (callable with no key), and registration is always **admin-approved**
— a request never auto-mints a key.

## Hosted skill file

Fresh agents should start from the hosted standard skill file:

```text
GET /mcp-skill/SKILL.md
```

It is unauthenticated, contains no secrets, and gives the model the MCP setup
sequence before it knows how to discover or call pdash tools. If the MCP server
is at `http://127.0.0.1:8090/mcp`, the skill file is at
`http://127.0.0.1:8090/mcp-skill/SKILL.md`.

Settings → MCP shows both the skill file URL and a self-contained copy-paste
instruction prompt. Prefer giving the agent the skill file URL first; the prompt
is the fallback for agents that cannot fetch the URL.

## The three ungated tools

| Tool | What it does | Backend endpoint |
|---|---|---|
| `onboarding` | Returns plain-language connect + registration instructions. No backend call. | — |
| `request_registration` | Creates a **pending** registration; returns a one-time `claim_token`. | `POST /internal/bootstrap/register` |
| `claim_registration` | Polls the request; returns the minted key once approved. | `POST /internal/bootstrap/claim` |

All three skip the `_require_agent` gate in `mcp/app/tools.py` (they are listed in
`BOOTSTRAP_TOOLS`, which also tags them `bootstrap` in the admin MCP catalog). The
MCP server forwards them to the backend with only the shared **service secret**
(no `X-Agent-Id` — there is no agent yet), exactly like `resolve-key`.

## MCP client setup first

Before calling any tool, the agent must **add this server to its MCP client
configuration** (streamable HTTP, URL ending in `/mcp`, **no** `Authorization`
header yet) and reload so pdash tools appear. Use MCP tool calls — not raw
`curl` against the JSON-RPC endpoint — unless debugging.

Settings → MCP has the hosted skill URL plus a copy-paste prompt with a concrete
config example and the URL your agent actually reaches (often your Tailscale
address, not the internal Docker hostname).

After `claim_registration` returns `hb_agt_...`, the agent updates the same MCP
config to add `"headers": { "Authorization": "Bearer hb_agt_..." }` and
reconnects. Gated tools stay locked until that step.

## The flow

```
client (no key)                 backend                         admin (web UI)
  │  request_registration          │                                │
  ├────────────────────────────────►  status=pending, claim_token   │
  │  ◄──────────────────────────────  (one-time)                     │
  │                                 │   appears in Approvals inbox ►│
  │  claim_registration(token)      │                                │  approve
  ├────────────────────────────────►  pending… pending…              │◄──
  │  ◄──────────────────────────────  (poll ~10s)                     │
  │  claim_registration(token)      │  status=approved + api_key      │
  ├────────────────────────────────►  (minted now, shown ONCE)        │
  │  ◄──────────────────────────────                                  │
  │  …all gated tools with Bearer hb_agt_…                            │
```

## After the agent has a key

The hosted skill (`GET /mcp-skill/SKILL.md`) and the ungated `onboarding` tool
cover this. Short version:

- Writes return `applied` | `pending` | `denied`. Never retry `pending` as a new
  write; poll `list_my_pending_requests` about every 5s.
- On a page the agent **owns**, ordinary widget creates and content/config/meta
  updates typically auto-apply. Home/system, `propose_page`, first `html` /
  `iframe` / `action_button`, deletes, and capability-shaped fields (iframe
  `src`, `action_target_id`, table columns, sandbox loosening, `confirm:
  true→false`) still land in Approvals.
- Extra JSON keys are ignored; `update_module` merges `data`/`config`.
  `get_module_schema` is optional — structured 400s name the field.

## Why mint-on-claim

The key is minted **only when the client claims it after approval**, not at
request time and not at approval time. Consequences:

- The plaintext key is **never stored at rest** — only the argon2 hash on the new
  `agents` row, exactly like every other agent. The admin never sees the key; the
  requesting client retrieves it itself (agent-first).
- The **claim token** (`hb_reg_…`, 256-bit random) is the only secret persisted,
  and only as a sha256 hash. It authenticates the poll to *its own* registration,
  is single-use (a `claimed` request never re-issues a key), and expires with the
  request (`PDASH_AGENT_REGISTRATION_TTL_SECONDS`, default 7 days).

`agent_registration_requests.status` moves `pending → approved → claimed`, or
`… → denied`, or `… → expired`. A real `agents` row (status `active`) is created
at claim and linked via `agent_id`. The claim window (`expires_at`) is bounded:
approval **refreshes** it, and a row past its window is expired — lazily on the
next claim poll (for `pending` *and* `approved`), refused at approve time, and
eagerly swept the next time anyone registers (there is no background daemon). The
admin can **deny an approved-but-unclaimed** registration too, so a row that
dead-ends (e.g. its name was taken by another agent before it was claimed) can
always be cleared.

## Admin surface

- **Approvals** inbox lists pending `register_agent` requests (session + CSRF via
  `/api/v1/approval-requests`). Approving may optionally override the display
  name / description / permissions via the approve body. The nav badge counts
  these alongside other pending approvals.
- **Settings → Agents** still lists registration rows for history (`/api/v1/agent-registrations`).
- **Settings → MCP** renders the hosted skill file URL and a copy-paste
  **onboarding prompt** (with an editable MCP URL) to drop into a fresh AI agent.

## Abuse bounds

The bootstrap path is reachable by any keyless MCP client (pdash is Tailscale-only,
single-admin). To keep it cautious:

- Outstanding **pending requests are capped** (`PDASH_AGENT_REGISTRATION_MAX_PENDING`,
  default 25) so the approval queue can't be flooded — excess returns
  `429 registration.queue_full`. Stale (time-expired) rows are swept before the
  count, so a burst of never-claimed requests can't permanently wedge the queue.
- `display_name` is globally unique; a clash is rejected at request, re-checked at
  approve, and re-checked at claim (`409 agent.name_taken`). A name already
  awaiting approval/pickup is also rejected (`409 registration.name_pending`) so
  duplicate live requests can't accumulate.
- `/register` intentionally signals whether a name is available (a small,
  unauthenticated existence check) — acceptable on a single-admin tailnet where
  agent display-names are just labels.
- Nothing here bypasses the approval engine for agent *writes* — that still gates
  every action once the agent is active.
