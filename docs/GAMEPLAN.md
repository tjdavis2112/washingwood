# Washingwood Fantasy Football: Gameplan

A private history site for the Washingwood league, at `washingwood.xyz`: standings, champions, records, drafts, trades and achievements from 2018 onward. We archive ESPN's raw data so we own it and can switch platforms later.

Decisions: `docs/adr/`. Terms: `GLOSSARY.md`.

Layout whiteboard: https://claude.ai/artifact/UviRRz54BkANGtVgwRpZ68

---

## Status

| Piece | State |
|---|---|
| ESPN API map | Done (from cwendt94/espn-api; not vendored in this repo) |
| Postgres schema | Done: `db/schema.sql`, loads on PG16, views tested on sample data |
| Raw archiver | Done: `scripts/archive_espn.py`, tested against a mocked API only |
| First real archive run (2018–2025) | **Next** |
| Loader (raw → core) | Not started; build it from the real archived JSON |
| Export (stats → JSON) | Not started |
| Frontend (v1) | Not started |
| Passphrase gate + deploy | Not started |

---

## Scope decisions

- **History starts in 2018.** 2017 (the first ESPN season) is left out on purpose and not archived.
- **No live data.** A Season is added once, after it ends.
- **Records follow the Owner**, never the team slot. Former owners keep their history.
- **Owners are shown by real name plus their Current team name.** No team logos.
- **Podium** = champion, runner-up, 3rd-place game winner. **Last place** = ESPN's final regular-season rank.

---

## Architecture

Three data layers. Each one can be rebuilt from the layer before it (ADR-0001).

1. **Raw**: untouched ESPN JSON in `archive/<league>/<year>/*.json`. Never edited.
2. **Core** (`core.*`): a platform-neutral model. ESPN IDs live only in `*_external_ids` tables (ADR-0002).
3. **Stats** (`stats.*`): derived SQL views (ADR-0003).

Stack:
- **Ingest/ETL**: Python (archiver + loader), managed with uv
- **DB**: Postgres 16 in Docker, **local only**, used as a build tool (ADR-0003)
- **Frontend**: Astro + React islands + Motion + Tailwind, static build (ADR-0006)
- **Hosting**: Cloudflare Pages, `washingwood.xyz` (bought through Cloudflare Registrar), with `washingwood.pages.dev` as the fallback
- **Access**: one shared passphrase checked by Cloudflare Pages middleware on every path, images included. HTTP-only cookie for about a year, `noindex` (ADR-0006).
- **Data location**: this repo is public and holds no league data. The archive, `owners.yaml` and Punishment content live in the private `washingwood-archive` repo. Exported JSON goes straight to Cloudflare (ADR-0007).

### Yearly update (after the championship week)

One local run: **archive** the finished season → **load** into Postgres → **export** stats to JSON → **build** the site → **deploy** to Cloudflare. Then commit the new raw files to `washingwood-archive`.

---

## Design direction

- Dark and sleek. Brand colors are **red, black and white**: black background, white text, red for highlights and buttons.
- **Gold, silver and bronze appear only on trophies and medals.**
- The **Podium** is a lit trophy case: 1st raised in the center, 2nd and 3rd lower on each side. It is not built from cards.
- **Interactive cards** (tilt, shine, flip) are for players, trades and similar items later. Not in v1.
- **Phone and desktop are both designed for.** Every page is checked at both widths, and nothing should look stretched or empty on desktop.
- Subtle motion: hover lifts, smooth page transitions.

---

## v1 scope

1. **Landing**: "Washingwood Fantasy Football" title and passphrase field. The only page served without the passphrase.
2. **Home**: current champion banner, trophy shelf (every Owner with titles and runner-ups, labeled with their Current team name), links into each Season.
3. **Season page** (2018–2025):
   - Podium (trophy case)
   - Last place, with a **Punishment** button that opens a popup with slots for picture, title and description. Shows "Punishment details coming soon" until filled in.
   - Final standings (record, PF/PA, seed)
   - Playoff bracket
   - Weekly results
   - **Scoring format** tab
   - Rosters, Draft, Transactions tabs: "Coming soon"
4. **Every other nav section** (Owners, Matchups, Record Book, Hall of Fame, Draft, Transactions, League Rules) is in the nav as a styled "Coming soon" page.

---

## Later (after v1)

Kept from the original plan; build in roughly this order.

- **Owners hub**: trophy case, career W-L, playoff appearances, roster per season, draft grades, trades, H2H vs every owner, badges
- **Matchups**: every matchup with box score cards; bracket history; championship feature cards; rivalry grid; closest games, blowouts, upsets
- **Record Book**: single week / season / all-time leaderboards, stat picker, team records, streaks, luck index, bench points, last-place history. Always show or filter by Scoring format.
- **Draft**: full board per year colored by Value over slot, grades, best/worst picks
- **Transactions**: trade cards with points each side scored after the trade; best waiver pickups
- **Hall of Fame**: legendary player seasons, curated in `core.hall_of_fame`
- **League Rules**: scoring and roster template by year, hand-written changelog (`core.rule_changes`), the league-wide Punishment explainer
- **Punishment content**: picture, title and description per Season, kept in `washingwood-archive`
- **Extras**: achievements/badges, manager efficiency (optimal lineup), auto-generated season recaps

---

## ESPN API quick reference

- Base: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl`
- League 2018+: `/seasons/{year}/segments/0/leagues/{id}`, falling back to `/leagueHistory/{id}?seasonId={year}` on 401
- The league is private: needs the `espn_s2` + `SWID` cookies from a member's account. The repo owner's account covers 2018+.
- `?view=` picks data slices; `?scoringPeriodId=` = NFL week; the `x-fantasy-filter` header (JSON) filters, sorts and pages
- Key views: `mSettings`, `mStatus`, `mTeam`, `mRoster`, `mMatchupScore` (+`mScoreboard` for box scores), `mStandings`, `mDraftDetail`, `mTransactions2`, `kona_player_info`, `kona_league_communication` (activity feed, under `/communication/`)
- Decoders are in cwendt94/espn-api `espn_api/football/constant.py` (not in this repo): `POSITION_MAP`, `PRO_TEAM_MAP`, `PLAYER_STATS_MAP`, `ACTIVITY_MAP`
- Player stats: `statSourceId` 0 = actual, 1 = projected; `scoringPeriodId` 0 = season total; skip `statSplitTypeId == 2`

### Data tiers by season
| Seasons | Tier | What we get |
|---|---|---|
| 2019+ | full | Weekly lineups incl. bench, player stats, box scores, transactions, activity |
| 2018 | partial | League-level data. The espn-api library blocks box scores/activity before 2019, so verify what ESPN actually returns on the first run |

---

## Schema summary (`db/schema.sql`)

- `raw.responses`: platform, league, season, resource, week, url, params, sha256, payload (deduped by hash)
- Identity: `core.leagues`, `league_platforms`, `owners`, `owner_external_ids`, `players`, `player_external_ids`
- Seasons/rules: `core.seasons` (data_tier, reception_points, te_premium, generated `scoring_label`, `scoring_rules` jsonb, `roster_slots` jsonb), `core.rule_changes`
- Teams: `core.franchises` (team in one season + final results), `core.franchise_owners` (franchise → person, supports co-owners)
- Games: `core.matchups` (playoff/bracket/championship flags, multi-week periods), `core.lineup_entries`, `core.player_week_stats`, `core.stat_definitions`
- Draft/txns: `core.draft_picks`, `core.transactions`, `core.transaction_items`
- Curated: `core.achievements`, `core.owner_achievements`, `core.hall_of_fame`
- Views: `stats.franchise_owner`, `team_games`, `podium`, `owner_career`, `head_to_head`, `player_franchise_season`, `player_season`, `draft_value`, `draft_grades`, `acquisition_impact`, `trade_scorecard`, `team_week_scores`, `all_play`

Not yet in the schema: Punishment (per-season title, description, image) and a way to mark the 3rd-place game. Add these when the loader is built.

---

## Archiver (`scripts/archive_espn.py`)

```bash
uv run python scripts/archive_espn.py --league-id <ID> --years 2018-2025 --out archive/
```
- Reads `ESPN_S2`, `ESPN_SWID` and `WASHINGWOOD_PG` (optional) from the environment
- Per season: league views, pro schedule, player list; for 2019+ also `player_pool`, per-week box scores / rosters / transactions, and the paginated activity feed
- `manifest.jsonl` logs every call, failures included
- Past seasons are reused from disk; `--force` refetches everything
- Unverified: the `player_pool` filter (`kona_player_info`, limit 2000). Check its output after the first run

---

## Next steps

1. **Create the private `washingwood-archive` repo** and clone it so `archive/` and `owners.yaml` live there.
2. **Run the archiver** for 2018–2025. Read `manifest.jsonl` for failures, especially in 2018.
3. **Inspect the real JSON** and confirm field paths: box score `rosterForCurrentScoringPeriod`, transaction items, draft picks, settings scoring items / `lineupSlotCounts`, and how the 3rd-place game and final ranks appear.
4. **Start Postgres** in Docker and load `db/schema.sql`.
5. **Write `owners.yaml`** (in the private repo): ESPN SWIDs / team IDs → person, per season.
6. **Write the loader** (`scripts/load_espn.py`): raw → core, idempotent per season. v1 needs only seasons/settings → owners → franchises → matchups (plus final ranks).
7. **Write the exporter**: `stats.*` → JSON for the Home and Season pages.
8. **Build the v1 frontend** (Astro), checked on both phone and desktop.
9. **Add the passphrase middleware and deploy** to Cloudflare Pages, then connect `washingwood.xyz`.

## Gotchas
- Team names change across years: always go through `franchise_owners`, never team name
- Playoff matchup periods can span 2 NFL weeks; `matchups` stores `first_week`/`last_week`
- Records across scoring formats aren't comparable: show the format or filter
- "Points after a trade" uses who actually started the player each week (`lineup_entries`), not the trade record
- Never put real owner names in this repo: code, tests, fixtures and issues use invented names (ADR-0007)
