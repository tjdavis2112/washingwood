# faintasy — League History App Gameplan

Custom web app for our ESPN fantasy football league: full history, stats, records, drafts, trades and achievements. We own the data so we don't depend on ESPN keeping it, and so we can switch platforms later.

Decisions: `docs/adr/`. Terms: `GLOSSARY.md`.

Layout whiteboard: https://claude.ai/artifact/UviRRz54BkANGtVgwRpZ68

---

## Status

| Piece | State |
|---|---|
| ESPN API map | Done (from cwendt94/espn-api; not vendored in this repo) |
| Postgres schema | Done: `db/schema.sql`, loads on PG16, views tested on sample data |
| Raw archiver | Done: `scripts/archive_espn.py`, tested against a mocked API only |
| First real archive run | **Next** |
| Loader (raw → core) | Not started; build it from the real archived JSON |
| API + frontend | Not started |

---

## Architecture

Three data layers. Each one can be rebuilt from the layer before it.

1. **Raw**: untouched ESPN JSON, on disk (`archive/<league>/<year>/*.json`) and optionally in `raw.responses`. Never edited. This is the insurance.
2. **Core** (`core.*`): a platform-neutral model. ESPN IDs live only in `*_external_ids` tables, so moving to Sleeper/Yahoo means writing a new importer, not a migration.
3. **Stats** (`stats.*`): derived views (draft value, trade winners, records, H2H...). Change a formula and history recomputes.

Stack:
- **DB**: Postgres (Supabase/Neon free tier is plenty; data is tens of thousands of rows per season)
- **Ingest/ETL**: Python (archiver + loader). Polars or pandas where useful.
- **API**: FastAPI (keeps everything in Python)
- **Frontend**: TBD (Next.js/React likely)
- **Refresh**: weekly cron reruns the archiver (past seasons come from cache, the live season is refetched), then the loader for the current season
- **Cheaper option**: data changes weekly, so we could precompute the stats layer to JSON and host a static site with no live API

---

## ESPN API quick reference

- Base: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl`
- League 2018+: `/seasons/{year}/segments/0/leagues/{id}`; before 2018: `/leagueHistory/{id}?seasonId={year}` (falls back to the other route on 401)
- Private leagues need the `espn_s2` + `SWID` cookies
- `?view=` picks data slices; `?scoringPeriodId=` = NFL week; the `x-fantasy-filter` header (JSON) filters, sorts and pages
- Key views: `mSettings`, `mStatus`, `mTeam`, `mRoster`, `mMatchupScore`(+`mScoreboard` for box scores), `mStandings`, `mDraftDetail`, `mTransactions2`, `kona_player_info`, `kona_league_communication` (activity feed, under `/communication/`)
- Decoders are in cwendt94/espn-api `espn_api/football/constant.py` (not in this repo): `POSITION_MAP`, `PRO_TEAM_MAP`, `PLAYER_STATS_MAP`, `ACTIVITY_MAP`
- Player stats: `statSourceId` 0 = actual, 1 = projected; `scoringPeriodId` 0 = season total; skip `statSplitTypeId == 2`

### Data tiers by season
| Seasons | What we get |
|---|---|
| 2019+ | Everything: weekly lineups incl. bench, player stats, box scores, transactions, activity |
| 2018 | League-level data on the modern endpoint; the library blocks box scores/activity/FA before 2019 (verify on our league) |
| ≤2017 | Archival: teams, owners, standings, matchup scores, draft, settings. No player stats, lineups or transactions |

Archival years are tagged "archival" in the UI. **Champions/podium must still show for every year.**
Optional: backfill player stat leaders for archival years from `nflverse` (we still won't know who rostered whom).

---

## App layout

Two hubs, **Seasons** and **Owners**. Everything else is a highlight section, and every player, owner and year links back to a hub.

### Home
- Current champion banner, trophy count per owner
- "This week in league history" card
- Rotating record-book highlights

### Seasons (hub, pick a year)
- Podium: 1st / 2nd / 3rd, plus last place
- Final standings (record, PF/PA, seed) + playoff bracket graphic
- Weekly results grid
- Tabs: **Rosters · Draft · Transactions · Scoring format**
- Archival years: champions, standings, draft only

### Owners (hub, one profile each)
- Trophy case: titles, runner-ups, records held
- Career W-L, playoff appearances, all-time points
- Roster for every season they played
- Draft grades by year, every trade and pickup
- H2H vs every other owner, badges earned

### Matchups
- Every matchup, filter by season / owner / week; each opens a box score card
- **Playoffs**: bracket history across all years
- **Championships**: a feature card per title game (score, top performers, margin)
- **Rivalries**: owner × owner H2H grid, colored by win %
- "Crazy" matchups: closest games, biggest blowouts, highest combined scores, biggest upsets vs projection

### Record Book
- Leaderboards: single week / single season / all-time
- Stat picker: points, rushing yds, receiving yds, TDs, other key formats
- Best & worst players for each stat
- Team records: highest/lowest weekly score, biggest blowout, closest game
- Streaks, luck index, bench points left
- Shame section: last-place history, worst weeks
- Records show the season's scoring format (or filter to same-format years), since PPR vs standard totals aren't comparable

### Hall of Fame
- Legendary player seasons: player, owner who drafted them, draft slot, total points, share of team points
- Impact line, e.g. "31% of team points, 11-3, won the title"
- Curated in `core.hall_of_fame`, backed by `stats.player_franchise_season`

### Draft
- Full board for every year (rounds × teams), cells colored by value vs. slot
- Grade per draft, all-time drafter ranking, best/worst picks ever, historically great drafts

### Transactions
- Trade cards: both sides side by side, points each side scored after the trade, winner computed
- Waiver pickups ranked by points scored as a starter after the add
- Craziest trades, most impactful pickups

### League Rules
- Scoring by year: PPR / 0.5 / standard, TE premium, other knobs
- Roster template by year (e.g. when FLEX was added)
- Changelog timeline of rule changes (`core.rule_changes`, written by hand)
- Source: `mSettings` each season

### Extras (cross-cutting)
- **Achievements/badges** awarded automatically: 200-point week, beat the weekly high scorer, won with the league's lowest score, perfect lineup
- **Manager efficiency**: actual vs. optimal lineup
- **Luck index**: actual record vs. all-play record
- **Season recap page**, auto-generated per year

---

## Schema summary (`db/schema.sql`)

- `raw.responses`: platform, league, season, resource, week, url, params, sha256, payload (deduped by hash)
- Identity: `core.leagues`, `league_platforms`, `owners`, `owner_external_ids`, `players`, `player_external_ids`
- Seasons/rules: `core.seasons` (data_tier, reception_points, te_premium, generated `scoring_label`, `scoring_rules` jsonb, `roster_slots` jsonb), `core.rule_changes`
- Teams: `core.franchises` (team in one season + final results), `core.franchise_owners` (franchise → person, supports co-owners)
- Games: `core.matchups` (playoff/bracket/championship flags, multi-week periods), `core.lineup_entries` (every player every week, bench too; generated `is_starter`), `core.player_week_stats` (raw stats jsonb with canonical keys, for re-scoring), `core.stat_definitions` (ESPN stat id → canonical key)
- Draft/txns: `core.draft_picks`, `core.transactions`, `core.transaction_items`
- Curated: `core.achievements`, `core.owner_achievements`, `core.hall_of_fame`
- Views: `stats.franchise_owner`, `team_games`, `podium`, `owner_career`, `head_to_head`, `player_franchise_season`, `player_season`, `draft_value`, `draft_grades`, `acquisition_impact`, `trade_scorecard`, `team_week_scores`, `all_play`

---

## Archiver (`scripts/archive_espn.py`)

```bash
python scripts/archive_espn.py --league-id <ID> --years 2012-2025 \
  --espn-s2 "$ESPN_S2" --swid "$ESPN_SWID" --out archive/ [--pg "$FAINTASY_PG"]
```
- Per season: league views, pro schedule, player list; for 2019+ also `player_pool`, per-week box scores / rosters / transactions, and the paginated activity feed
- `manifest.jsonl` logs every call, failures included
- Past seasons are cached on disk; the live season always refetches (`--force` refetches everything)
- Unverified: the `player_pool` filter (`kona_player_info`, limit 2000). Check its output after the first run

---

## Next steps

1. **Run the archiver** for every season the league has existed. Read `manifest.jsonl` for failures, especially 2018 and pre-2018 views.
2. **Inspect the real JSON** and confirm field paths (box score `rosterForCurrentScoringPeriod`, transaction items, draft picks, settings scoring items / `lineupSlotCounts`).
3. **Create the DB**: `psql "$FAINTASY_PG" -f db/schema.sql`
4. **Write the loader** (`scripts/load_espn.py`): raw → core, idempotent per season. Order: seasons/settings → owners (manual mapping file) → franchises → players + external IDs → matchups → lineup entries + player week stats → draft → transactions.
5. **Owner mapping**: a hand-maintained `owners.yaml` mapping ESPN SWIDs / team IDs → person, per season.
6. **Player ID crosswalk**: seed `player_external_ids` from the DynastyProcess / nflverse ID map so future platforms line up.
7. **Python-side calcs**: optimal lineup (FLEX makes it an assignment problem) → efficiency; achievements engine → `owner_achievements`.
8. **API** (FastAPI) over the `stats.*` views, one endpoint group per nav section.
9. **Frontend**: build in this order: Seasons → Owners → Matchups → Record Book → Draft → Transactions → Hall of Fame → League Rules → Home.
10. **Weekly cron**: archiver + loader for the current season.

## Gotchas
- Team names and owners change across years: always go through `franchise_owners`, never team name
- "Points after a trade" uses who actually started the player each week (`lineup_entries`), not the trade record
- Playoff matchup periods can span 2 NFL weeks; `matchups` stores `first_week`/`last_week`
- Records across scoring formats aren't comparable: show the format or filter
- Old private seasons need cookies from an account that was in the league that year
