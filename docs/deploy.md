# Deployment guide

For **local development** (native processes, hot reload), see [dev.md](dev.md).

Home Base is designed for a single-admin homelab box, fronted by Caddy, and
network-gated by Tailscale. The whole stack runs as four containers under
Docker Compose: `backend`, `mcp`, `frontend`, and `caddy`.

## Prerequisites

- A Linux host with **Docker** + **Docker Compose v2** installed.
- The host must already be **on your tailnet**. Verify with `tailscale status`.
- (Optional) A Tailscale-issued cert for the host's tailnet name; see "TLS"
  below for the alternative.

## First-run flow

```bash
# 1. Clone the repo
git clone <repo-url> ~/pdash && cd ~/pdash

# 2. Copy the env template and edit secrets
cp .env.example .env
# Set a strong PDASH_BOOTSTRAP_ADMIN_PASSWORD (we'll remove it after step 4).

# 3. First-run init: builds images, then runs the backend's CLI bootstrap.
docker compose build
docker compose run --rm \
    -e PDASH_BOOTSTRAP_ADMIN_PASSWORD="$(grep -oE '^PDASH_BOOTSTRAP_ADMIN_PASSWORD=.*' .env | cut -d= -f2-)" \
    backend python -m app.cli init \
        --admin-password "$(grep -oE '^PDASH_BOOTSTRAP_ADMIN_PASSWORD=.*' .env | cut -d= -f2-)"

# This prints the *service secret* on stdout. Paste it into .env as
# PDASH_SERVICE_SECRET=<value>.

# 4. Comment out / remove PDASH_BOOTSTRAP_ADMIN_PASSWORD from .env so the
#    secret isn't left lying around. Then bring the stack up:
docker compose up -d

# 5. Confirm health:
docker compose ps
curl -sf http://localhost:8080/healthz   # via Caddy → frontend
```

Alternative: launch `backend` once with `PDASH_BOOTSTRAP_ADMIN_PASSWORD` in
the environment; the entrypoint will run the init the first time it sees no
DB file, then refuse to overwrite on subsequent boots. Either path works.

## Wiring to Tailscale

Three reasonable setups, in order of recommendation:

### A. `tailscale serve` + Caddy `tls internal` (simplest)

```bash
# Once the stack is up:
tailscale serve --https=443 localhost:8443
# Optionally proxy plain HTTP as well:
tailscale serve --http=80 localhost:8080
```

`tailscale serve` terminates TLS using Tailscale's own MagicDNS cert, then
proxies cleartext to Caddy on `localhost:8443`. Caddy uses its `tls
internal` self-signed cert for the inner hop — fine because Tailscale never
exposes that cert outside the tailnet.

### B. Tailscale-issued cert mounted into Caddy

```bash
# On the host:
tailscale cert <host>.<tailnet>.ts.net
# This writes <host>.<tailnet>.ts.net.crt and .key into the current dir.
sudo mkdir -p /var/lib/tailscale/certs
sudo cp <host>.<tailnet>.ts.net.* /var/lib/tailscale/certs/
sudo chown -R root:root /var/lib/tailscale/certs
```

In `docker-compose.yml`, uncomment the `/var/lib/tailscale/certs` volume
mount on the `caddy` service. In the `Caddyfile`, uncomment the
`https://<YOUR-TAILNET-HOSTNAME>.ts.net` block and put the path to the cert
files. Then `docker compose up -d caddy`.

### C. Cleartext (only for testing inside the tailnet)

Skip TLS termination at Caddy entirely and bind it to `:80`. Tailscale ACLs
keep this safe inside the tailnet, but browsers won't store cookies
securely. Not recommended for daily use.

## Updating

```bash
cd ~/pdash
git pull
docker compose build
docker compose up -d
```

Compose will recreate containers whose images changed. SQLite migrations
auto-apply on backend startup (the entrypoint runs `alembic upgrade head`).

## Backups

Run the bundled script (or wire it to cron):

```bash
./scripts/backup.sh
# Writes data/backups/pdash-YYYYMMDDTHHMMSS.db.tar.gz
# Rotates to keep last 30 daily + last 12 monthly.
```

### Sample crontab entry

```cron
# At 03:15 every night, take a SQLite-consistent snapshot.
15 3 * * * cd /home/admin/pdash && ./scripts/backup.sh >> data/backups/cron.log 2>&1
```

### Restore from a backup

```bash
docker compose stop backend mcp
tar -xzf data/backups/pdash-<timestamp>.db.tar.gz -C data/
mv data/pdash-<timestamp>.db data/pdash.db
docker compose start backend mcp
```

## Common operations

```bash
# Tail logs:
docker compose logs -f --tail=200 backend

# Restart everything:
docker compose restart

# Run an arbitrary backend CLI command (e.g. ad-hoc migration rollback):
docker compose run --rm backend alembic downgrade -1

# Open a SQLite shell against the live DB (use read-only mode!):
docker compose exec backend sqlite3 -readonly /data/pdash.db
```

## Backend bootstrap cheatsheet

The `python -m app.cli init` command:

1. Creates `pdash.db` at `$PDASH_DATABASE_PATH`.
2. Runs all Alembic migrations.
3. Hashes the admin password with argon2id and stores it in `kv_settings`.
4. Generates the signing secret (used to sign the session cookie) and the
   service secret (used by the MCP server to call `/api/v1/internal/*`).
5. Prints the service secret to stdout. **Capture it now** — it isn't
   retrievable later without inspecting the SQLite file.

The signing secret can be rotated by overwriting `kv_settings.signing_secret`
in SQLite (this invalidates all sessions). The service secret can be
rotated the same way; restart the MCP server after rotation.
