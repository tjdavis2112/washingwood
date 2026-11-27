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
$env:SITE_DATA_DIR = "../contract/examples"; npm run dev
```
- `$env:SITE_DATA_DIR = ...`: sets the data folder for this PowerShell session. It's required, and the build fails without it, so it can't silently use the wrong data.
- `npm run dev`: a live-reloading local server, for working on pages.

## Rules

- Every page is checked at phone and desktop widths. The page must never scroll sideways: wide content scrolls inside its own container.
- No team logos, and no requests to third-party hosts. The layout tests catch third-party requests and logo `<img>` tags. A logo drawn in CSS or SVG would get past them, so check the screenshots too.
- An unknown path returns a real 404. Without `404.html`, Cloudflare Pages would serve Home with status 200 instead.
