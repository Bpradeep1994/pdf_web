# Cloudflare setup — global reach, TLS, DDoS protection (free tier)

Cloudflare sits in front of your single VPS and serves your app from its global edge
network. This is what makes one server feel fast worldwide, and shields it from attacks.

```
  Users worldwide → Cloudflare edge (200+ cities) → your VPS origin
```

## 1. Add your domain to Cloudflare
1. Create a free account at cloudflare.com → **Add a site** → enter your domain.
2. Cloudflare gives you two **nameservers** → set them at your registrar (where you bought the domain).
3. Wait for "Active" (a few minutes to a few hours).

## 2. DNS records (point at your VPS)
Under **DNS → Records**, add (replace `1.2.3.4` with your VPS IP):

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `app` | `1.2.3.4` | 🟠 Proxied |
| A | `api` | `1.2.3.4` | 🟠 Proxied |

**Proxied (orange cloud) = ON** — that's what routes traffic through Cloudflare's edge.

These must match `DOMAIN_APP=app.yourdomain.com` / `DOMAIN_API=api.yourdomain.com` in `.env.production`.

## 3. TLS mode
**SSL/TLS → Overview → Full (strict)**. Caddy on your VPS provisions a real Let's Encrypt
cert; Cloudflare validates it end-to-end. (Do **not** use "Flexible" — it's insecure.)

> Note: with Cloudflare proxying, ports 80/443 must still be open on the VPS for Caddy
> to complete the Let's Encrypt challenge and receive traffic.

## 4. Recommended settings
- **Speed → Optimization**: enable Auto Minify + Brotli.
- **Caching → Configuration**: Standard. Static assets cache at the edge automatically.
- **Security → Settings**: Security level = Medium; enable **Bot Fight Mode** (free).
- **Rules → Page Rules** (optional): cache-everything on `app.yourdomain.com/_next/static/*`.
- **Network**: enable **WebSockets** (required for live collaboration).

## 5. VPS firewall (defense in depth)
Only the web ports should face the internet. The prod compose already binds Postgres/Redis/etc.
to `127.0.0.1`, but also set a firewall:

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```
> Docker can bypass ufw for published ports — that's why the prod compose binds infra to
> `127.0.0.1` (not `0.0.0.0`). Keep both.

## 6. If you add a Content-Security-Policy
The app sets none by default. If you add one (Cloudflare **Rules → Transform Rules → Response
Headers**, or in Caddy), allow the Razorpay checkout widget:
```
script-src  'self' 'unsafe-inline' https://checkout.razorpay.com;
frame-src   https://api.razorpay.com https://checkout.razorpay.com;
connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com;
img-src     'self' data: https:;
```

## Result
- `https://app.yourdomain.com` served globally with automatic TLS + DDoS protection.
- Origin IP hidden behind Cloudflare.
- Static assets cached at the edge → fast for users everywhere.
