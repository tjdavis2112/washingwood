# The site (`site/`)

A static Astro site. Every page is rendered at build time from the site-data JSON (`contract/`). Nothing is fetched at runtime, and the site never calls ESPN (ADR-0006).

## Pieces

| Path | What it does |
| --- | --- |
| `src/data/site-data.ts` | Reads JSON from `SITE_DATA_DIR` and checks it against `contract/site-data.schema.json` (Ajv). Bad or missing data stops the build. |
| `src/sections.ts` | The nav sections, in order. A section with `built: false` gets the shared "Coming soon" page. |
| `src/layouts/Base.astro` | Every page's shell: head (`noindex`), header and nav. |
| `src/styles/global.css` | Tailwind plus the design tokens. Red, black and white; gold, silver and bronze for trophies only. |
| `src/components/ChampionBanner.tsx` | Home's Champion banner. A React island used only for Motion's hover lift; its text is in the built HTML. |
| `wrangler.toml` | Cloudflare Pages config, used locally by `wrangler pages dev`. |
| `functions/_middleware.ts` | The passphrase gate. It runs before every request on Cloudflare Pages (and under `wrangler pages dev`). |
| `src/pages/enter.astro` | The landing screen, the only page served without the passphrase. |
| `public/robots.txt` | Disallows all crawlers. |

## Commands (run in `site/`)

```powershell
npm install
```
- Installs the site's packages into `site/node_modules`. Run it once, and again after `package.json` changes.

```powershell
npx playwright install chromium
```
- Downloads the browser Playwright drives. Run it once per machine.

```powershell
npm test
```
- Builds the site from the invented examples in `contract/examples`, serves it with `wrangler pages dev` (Cloudflare's local Pages server), and runs the Playwright tests at 375px (phone) and 1280px (desktop).
- Saves a full-page screenshot of every page to `test-results/screenshots/<phone|desktop>/` for review. That folder is gitignored.

```powershell
npx astro check
```
- Typechecks the `.astro`, `.ts` and `.tsx` files.

```powershell
npx tsc -p functions
```
- Typechecks the middleware against Cloudflare's Workers types.

```powershell
$env:SITE_DATA_DIR = "../contract/examples"; npm run dev
```
- `$env:SITE_DATA_DIR = ...`: sets the data folder for this PowerShell session. It's required, and the build fails without it, so it can't silently use the wrong data.
- `npm run dev`: a live-reloading local server, for working on pages.

## The passphrase gate (ADR-0006)

How a request is handled:

1. **Every response** gets these headers:
   - `X-Robots-Tag: noindex, nofollow`
   - `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'` (the site can't be framed)
   - `Referrer-Policy: same-origin`
   - `Cache-Control: private, no-cache` (no shared cache keeps league pages)
2. **A secret is missing** (`SITE_PASSPHRASE` or `SESSION_KEY`): everything is refused (503), including `robots.txt`. The gate fails closed.
3. **`/robots.txt`** is served.
4. **`/enter/`** shows the landing screen. Posting the form checks the passphrase:
   - **Wrong:** the same screen with "That passphrase isn't right. Try again." (status 401, no cookie).
   - **Right:** sets the `ww_session` cookie and redirects to Home.
5. **Any other path with a valid cookie:** served normally.
6. **Any other path without one:** a page request redirects to `/enter/`; anything else (data, images, scripts) gets 401.

The cookie (`__Host-ww_session`):
- It is `HttpOnly` (scripts can't read it), `Secure` (HTTPS only), `SameSite=Lax`, and lasts 365 days. The `__Host-` prefix makes browsers reject it unless it's Secure, `Path=/` and has no Domain, so a subdomain can't plant one.
- Its value is HMAC-SHA256 over the passphrase, keyed by `SESSION_KEY`. It never contains the passphrase. Without `SESSION_KEY`, a stolen cookie can't be used to guess the passphrase offline.
- **Changing either secret** changes the value every cookie must match, so everyone is signed out at once.
- Passphrase and cookie checks compare fixed-length values without stopping at the first difference, so response timing doesn't leak how close a guess was.

CSS is inlined into each page, so the landing screen needs no other file and nothing under `/_astro/` is ever public. That folder is where built images would go.

### Running it locally

`npm run dev` (Astro's dev server) does **not** run the middleware. To try the gate yourself:

1. **Create `site/.dev.vars`**, which is gitignored and holds Wrangler's local secrets:
   ```
   SITE_PASSPHRASE=pick-a-local-test-phrase
   SESSION_KEY=any-long-random-local-string
   ```
2. **Build, then serve:**
   ```powershell
   $env:SITE_DATA_DIR = "../contract/examples"; npm run build; npm run serve
   ```
   - `npm run build`: writes the static site to `dist/`.
   - `npm run serve`: `wrangler pages dev`, which serves `dist/` with the middleware on http://127.0.0.1:8788.

### Tests

`tests/gate.spec.ts` runs with no cookie. It checks the redirects and 401s, the wrong-passphrase message, the cookie's flags and lifetime, the headers and `robots.txt`.

It also starts extra servers over the same build with different secrets (`tests/servers.ts`), to check that:
- a new passphrase rejects old cookies
- a different `SESSION_KEY` gives a different cookie, and each server rejects the other's
- a missing `SESSION_KEY` fails closed

The other tests sign in once (`tests/auth.setup.ts`) and reuse the cookie.

On Windows, Wrangler's `workerd` process can outlive its parent. `servers.ts` stops each extra server by port as well, and refuses to start if a port is already in use, so a leftover server can't answer with the wrong secrets.

Screenshots are taken with reduced motion on, so they show settled pages rather than a page transition mid-fade.

### Deploy checklist (for #11)

1. **Set both secrets** in the Cloudflare Pages project (Settings → Variables and Secrets, as *Secret*):
   - `SITE_PASSPHRASE`: the shared passphrase. Make it long; several random words.
   - `SESSION_KEY`: 32+ random bytes. To generate one: `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`
2. **Add a rate-limiting rule** (Security → WAF → Rate limiting rules) so passphrase guessing is throttled:
   - Match: `http.request.uri.path eq "/enter/"` and `http.request.method eq "POST"`
   - Limit: about 10 requests per minute per IP. Action: Block for 10 minutes.
3. **To sign everyone out**, change `SITE_PASSPHRASE` (and tell members) or `SESSION_KEY` (members re-enter the same passphrase).

## Rules

- Every page is checked at phone and desktop widths. The page must never scroll sideways: wide content scrolls inside its own container.
- No team logos, and no requests to third-party hosts. The layout tests catch third-party requests and logo `<img>` tags. A logo drawn in CSS or SVG would get past them, so check the screenshots too.
- An unknown path returns a real 404. Without `404.html`, Cloudflare Pages would serve Home with status 200 instead.
