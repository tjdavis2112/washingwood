# Static site on Cloudflare Pages, gated by a passphrase checked at the edge

Data changes once a year (a **Season** is added after it ends), so the site is a static Astro build deployed to Cloudflare Pages, with no API server or hosted database. The site is on the public internet for league members, so one shared passphrase is checked by Cloudflare Pages middleware before any page, data file or image is served. Only the landing screen is served without it. On success it sets an HTTP-only cookie lasting about a year. The passphrase is rotated through one environment variable, and every response is marked `noindex`.

## Status

accepted. Supersedes ADR-0004's API choice (FastAPI). Python is still used for ingest and ETL.

## Considered Options

- **FastAPI + hosted Postgres**: a real server-side check, but a server and database running all year for data that changes yearly. Rejected.
- **Passphrase checked in browser JavaScript**: free and simple, but anyone can read the page source or fetch the JSON directly, so it isn't access control. Rejected.

## Consequences

- No per-user accounts or MFA. Anyone with the passphrase sees everything, which is acceptable because the data isn't highly sensitive.
- Punishment photos show real league members, so the gate must cover images too. Don't add a path that skips the middleware.
- Frontend: Astro + React islands (Motion, Tailwind) for interactive parts.
