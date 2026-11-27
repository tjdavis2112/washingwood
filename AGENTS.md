# washingwood

League history app for our ESPN fantasy football league ("faintasy"): full history, records, drafts, trades, achievements. We archive ESPN's raw data so we own it and can switch platforms later.

Read `docs/GAMEPLAN.md` for scope, roadmap and app layout before planning new work.

## Layout

- `scripts/archive_espn.py`: pulls raw ESPN JSON to `archive/<league>/<year>/` (and optionally `raw.responses`)
- `db/schema.sql`: Postgres schema, three layers `raw` → `core` → `stats`
- `docs/GAMEPLAN.md`: roadmap, app layout, ESPN API notes, gotchas
- `docs/adr/`: decisions already made. Read the relevant ones before changing architecture.
- `GLOSSARY.md`: domain terms. Use these words in code, issues and tests.
- `tests/`: pytest

## Commands

- `uv sync`: install dependencies into `.venv`
- `uv run pytest`: run tests
- `uv run ruff check .` / `uv run ruff format .`: lint and format
- `uv run python scripts/archive_espn.py --help`: archiver usage

## Rules

- Never edit files under `archive/` or rows in `raw.responses`. Raw is the source of truth (ADR-0001).
- ESPN IDs never become keys in `core.*`. They go in `*_external_ids` tables (ADR-0002).
- Go through `core.franchise_owners` to reach an **Owner**. Never join on team name.
- Secrets (`ESPN_S2`, `ESPN_SWID`, `FAINTASY_PG`) come from the environment or `.env`. Never commit them or print them in logs.
- When a hard-to-reverse decision gets made, record it as an ADR (see the `domain-modeling` skill).

## Agent skills

### Issue tracker

Issues and specs are GitHub Issues on `tjdavis2112/washingwood`, managed with `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.
