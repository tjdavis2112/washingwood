# washingwood

Washingwood Fantasy Football: a passphrase-gated static history site for our ESPN league, 2018 onward. We archive ESPN's raw data so we own it and can switch platforms later.

Read `docs/GAMEPLAN.md` for scope, v1 definition, design direction and roadmap before planning new work.

## Layout

- `scripts/archive_espn.py`: pulls raw ESPN JSON to `archive/<league>/<year>/`
- `src/washingwood/`: pipeline package. `build` (archive → Postgres → site data), `loader`, `owners`, `export`, `contract`
- `site/`: Astro static site, rendered only from site-data JSON (`SITE_DATA_DIR`); Playwright tests in `site/tests/`
- `db/schema.sql`: Postgres schema, three layers `raw` → `core` → `stats`
- `contract/`: site-data contract (JSON Schema + invented example fixtures) between pipeline and site; `washingwood.contract` validates against it
- `docs/GAMEPLAN.md`: scope, v1, design direction, ESPN API notes, gotchas
- `docs/adr/`: decisions already made. Read the relevant ones before changing architecture.
- `GLOSSARY.md`: domain terms. Use these words in code, issues and tests.
- `tests/`: pytest
- `archive/`, `owners.yaml`: **not in this repo**. They live in the private `washingwood-archive` repo (ADR-0007).

## Commands

- `uv sync`: install dependencies into `.venv`
- `uv run pytest`: run tests
- `uv run ruff check .` / `uv run ruff format .`: lint and format
- `uv run python scripts/archive_espn.py --help`: archiver usage
- In `site/`: `npm test` (build from `contract/examples` + Playwright at phone and desktop widths; screenshots in `site/test-results/screenshots/`), `npx astro check` and `npx tsc -p functions` (typecheck site and middleware)
- `uv run python -m washingwood.build --help`: build site data (see `docs/guides/build-site-data.md`). Postgres-backed tests need Docker Desktop running.

## Rules

- **This repo is public.** Never commit league data: no raw archive, exported JSON, real owner names, ESPN IDs, or Punishment content. Tests and fixtures use invented names (ADR-0007).
- Never edit archive files or rows in `raw.responses`. Raw is the source of truth (ADR-0001).
- ESPN IDs never become keys in `core.*`. They go in `*_external_ids` tables (ADR-0002).
- Go through `core.franchise_owners` to reach an **Owner**. Never join on team name.
- Every path on the deployed site, images included, sits behind the passphrase middleware. Only the landing screen is served without it (ADR-0006).
- Secrets (`ESPN_S2`, `ESPN_SWID`, `WASHINGWOOD_PG`, the site passphrase) come from the environment or `.env`. Never commit them or print them in logs.
- UI work is checked at both phone and desktop widths before it counts as done.
- When a hard-to-reverse decision gets made, record it as an ADR (see the `domain-modeling` skill).

## Agent skills

### Issue tracker

Issues and specs are GitHub Issues on `tjdavis2112/washingwood`, managed with `gh`. See `docs/agents/issue-tracker.md`. Issues are public too: no league data in them.

### Triage labels

Default five labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.
