# Gatehouse deployment troubleshooting

Read the section matching the observed failure. Collect evidence before mutating services.

## Compose shows only the API

Symptoms include a healthy `api`, a `web` service that is `Created` or absent, and an existing `docker-proxy` listener on the configured host port.

Inspect:

```bash
docker compose ps -a
docker compose logs web --tail=100
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -lntp | grep '<port>'
```

If another named project owns the port, preserve it and assign Gatehouse a different loopback port. Recreate Gatehouse, update only its Caddy upstream, and test locally before reloading Caddy.

## Public health returns the wrong body

Gatehouse's health route returns `{"status":"ok"}`. A plain `ok`, another payload, or headers identifying a different stack means Caddy reached the wrong local port.

Compare:

```bash
curl -i http://127.0.0.1:<gatehouse-port>/health
curl -i https://<gatehouse-domain>/health
```

Inspect all Caddy site blocks and Docker port ownership. Do not infer success from HTTP 200 alone.

## TLS alert internal error

An error such as `tlsv1 alert internal error` commonly means Caddy has no usable certificate for the requested hostname.

Check DNS first:

```bash
dig +short A <domain>
dig +short AAAA <domain>
dig +short CAA <domain>
```

Then inspect Caddy's effective configuration and recent issuance logs:

```bash
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl cat caddy | grep ExecStart
journalctl -u caddy --since '10 minutes ago' --no-pager
```

The automatic TLS log must list the failing hostname. If it lists only another hostname, make the intended hostname an explicit site block, reload once, and inspect the new log. Avoid repeated restarts and do not delete `/var/lib/caddy`; both actions can make recovery harder or trigger certificate-authority rate limits.

The OCSP warning `no OCSP server specified in certificate` is not by itself a certificate issuance failure.

## Caddy validates but does not serve the edited domain

Confirm that systemd loads `/etc/caddy/Caddyfile`, that the file was actually saved, and that no formatting artifacts such as Markdown fences or escaped directives remain. Use `reverse_proxy`, not `reverse\_proxy`.

Prefer separate site blocks while diagnosing. After reload, look for an automatic TLS domain list containing every intended hostname.

## Application startup fails

Inspect:

```bash
docker compose config
docker compose logs api --tail=200
```

Common Gatehouse-specific causes are a missing `.env`, an example or short `SESSION_SECRET`, an example or short `ADMIN_PASSWORD`, and an unwritable data path. Fix configuration without printing secret values, recreate the service, and recheck health.

## Browser login or API calls fail after health succeeds

- Remove trailing slashes from `ALLOWED_ORIGINS` and include the exact HTTPS origin used by the browser.
- Confirm the provider base URL uses HTTPS unless insecure upstreams were intentionally enabled for local testing.
- Confirm the gateway key is bound to the exact requested model.
- Check account model authorization, RPM, and shared token quota.
- Use `docker compose logs -f --tail=100` during one reproduction, then stop following with Ctrl+C.

## Safe rollback

If a Caddy change broke another application, restore the previously inspected site block or backup, validate, and reload. If a Gatehouse image update fails, keep the data volume and `.env`, return to the previously known Git revision or image, and recreate the services. Never delete the database volume as a routine rollback.
