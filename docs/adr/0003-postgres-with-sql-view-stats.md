# Postgres as a local build tool, with derived stats as SQL views

Data is small (tens of thousands of rows per season) and relational (owners, franchises, matchups, lineups), so the model lives in Postgres. Since the site is static (ADR-0006), Postgres 16 runs only on your machine in Docker. It's used to load the **Archive**, compute stats and export JSON, and is never exposed to the internet. Derived numbers such as draft value, trade scorecards, head-to-head and all-play are `stats.*` views, not stored tables, so changing a formula recomputes all history.

## Considered Options

- **DuckDB**: no server needed, but the schema (generated columns, jsonb) would have to be ported. Rejected while Docker is available.

## Consequences

- Calculations that are hard in SQL (optimal lineup with FLEX, the achievements engine) run in Python and write to `core` tables.
- The database can be dropped and rebuilt from the Archive at any time (ADR-0001), so it needs no backup of its own.
