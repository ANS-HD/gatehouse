---
name: gatehouse-racknerd-deploy
description: Deploy, update, verify, and troubleshoot the Gatehouse Docker Compose application on a RackNerd Ubuntu VPS behind Caddy HTTPS. Use for first-time Gatehouse VPS deployment, domain cutover, local-port conflicts, certificate failures, health checks, and safe updates; do not use for unrelated hosting stacks.
---

# Gatehouse on RackNerd

Deploy Gatehouse without disrupting unrelated services already running on the VPS. Treat the repository's `README.md`, `.env.example`, `docker-compose.yml`, and application health route as the source of truth; inspect them before relying on the examples below.

## Establish the deployment facts

Resolve the VPS address and SSH user, repository and install directory, public application domain, free loopback web port, and any existing Caddy or Docker Compose services before changing the server.

Inventory first:

```bash
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -lntp
systemctl status caddy --no-pager
```

Do not stop or remove an unknown container merely because it occupies Gatehouse's default port. Preserve existing domain-to-port mappings and select another loopback port for Gatehouse.

## Prepare Gatehouse

Clone or update the repository in the chosen install directory. Preserve an existing `.env`, database volume, and `SESSION_SECRET` during updates.

Create `.env` from `.env.example` on first deployment. Require:

- A new strong `ADMIN_PASSWORD`; never echo it into logs or responses.
- `SESSION_SECRET` generated with `openssl rand -hex 32`, never the example placeholder. Do not rotate it after data exists unless the user accepts that encrypted provider credentials and detailed logs become unreadable.
- `DATABASE_PATH=/data/gateway.db` for the supplied Compose volume.
- `ALLOWED_ORIGINS` containing exact HTTPS origins with no trailing slash.
- `ALLOW_INSECURE_UPSTREAMS=false` in production.
- `REGISTRATION_ENABLED=false` unless public registration is intentional.

An upstream API key may remain empty and be added later through the admin UI.

Validate before starting:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
docker compose logs --tail=100
```

The API must become healthy and the web service must be running. A web service stuck in `Created` commonly indicates a published-port collision.

## Allocate the local web port safely

The supplied Compose file publishes the web service only on loopback. Keep that property. If `127.0.0.1:8080` is occupied, use another free port such as `8081` and update only Gatehouse's published web port:

```yaml
ports:
  - "127.0.0.1:8081:80"
```

Record the local port because Caddy must proxy to it. Verify the application locally before touching public routing:

```bash
curl -i http://127.0.0.1:8081/health
```

For this repository, the expected body is `{"status":"ok"}`. A different body is evidence that the request reached another service.

## Configure DNS and Caddy

Require the domain's public A record to resolve to the VPS before certificate issuance. Check A, AAAA, and CAA records. An obsolete AAAA record can send validation traffic to the wrong server.

Use a distinct Caddy site block for each application. Never point an existing application's domain at Gatehouse merely to reuse a certificate:

```caddy
gateway.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8081
}

existing.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
}
```

Before overwriting an existing Caddyfile, inspect and preserve every unrelated site block. Then format, validate, and reload:

```bash
caddy fmt --overwrite /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy
```

Keep ports 80 and 443 reachable publicly and keep the application port bound to `127.0.0.1`. Do not expose FastAPI's port 8000.

## Verify end to end

Verify each layer independently:

```bash
docker compose ps
curl -i http://127.0.0.1:<local-port>/health
curl -i https://<public-domain>/health
```

Then open the HTTPS site, sign in with the administrator account, add a provider and allowed model, create a model-bound `gw_...` key, and send one minimal request through `/v1/chat/completions` or `/v1/responses`. Avoid putting gateway or upstream keys directly into reusable shell history; use a temporary environment variable and unset it afterward.

## Update and recover

Before an update, run the repository backup script and preserve `.env`. Then pull with fast-forward only and recreate the services:

```bash
./deploy/backup.sh
git pull --ff-only
docker compose up -d --build
```

Verify both the local and public health endpoints after every change. If ports, TLS, or routing fail, read [references/troubleshooting.md](references/troubleshooting.md) before changing unrelated services or deleting Caddy state.
