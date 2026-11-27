# Postgres, with derived stats as SQL views

Data is small (tens of thousands of rows per season) and relational (owners, franchises, matchups, lineups), so we use Postgres (a Supabase/Neon free tier is enough). Derived numbers such as draft value, trade scorecards, head-to-head and all-play are `stats.*` views, not stored tables, so changing a formula recomputes all history.

## Consequences

- Calculations that are hard in SQL (optimal lineup with FLEX, the achievements engine) run in Python and write to `core` tables.
- If views get slow, materialize them or precompute to JSON for a static site (see GAMEPLAN "Cheaper option"). Don't denormalize `core`.
