# ESPN Fantasy Football API: field map for the loader

What this is: the field paths and enum meanings the loader needs to turn the raw ESPN archive
(`archive/<leagueId>/<year>/*.json`) into `core.*` (`db/schema.sql`). ESPN publishes no docs, so
every claim is tied to one of two primary sources:

- **The archived JSON itself** (ground truth). Cited as **[observed: <resource>, seasons X–Y]**.
- **cwendt94/espn-api** at commit `700e15ddbb91124f031473d2411c8a6285944274` (committed
  2026-10-19), cited as **[source: <path>@700e15d#Lnn]**. Paths are relative to the repo root.

Anything not directly in either source is labelled **Inferred**. When the library and the data
disagree, the data wins and the conflict is called out.

This file is for a public repo. It contains no league ID, team or member names, member IDs, team
IDs tied to people, or league score values.

## Seasons examined

| Season | Route used by the archiver | What is usable |
|---|---|---|
| 2018 | `/seasons/2018/...` | Everything, all 17 weeks. Analysed. |
| 2019 | `/leagueHistory/<leagueId>?seasonId=2019` (fallback after a 401) | League-level views only. Not representative; see [2019 and the leagueHistory route](#2019-and-the-leaguehistory-route). |
| 2020–2025 | `/seasons/<year>/...` | Everything, all 17 weeks. Analysed. |

[observed: manifest.jsonl, seasons 2018–2025]. 2025 was the primary season. All checks marked
"seasons 2018, 2020–2025" were run over every one of those seasons.

## How the archive was fetched

The scraper is `scripts/archive_espn.py`. Base URL `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl`.

| File | Endpoint | Params | `x-fantasy-filter` header |
|---|---|---|---|
| `league_m{Settings,Status,Team,Roster,MatchupScore,Standings,DraftDetail}.json` | league route | `view=<one view>` | none |
| `pro_schedule.json` | `/seasons/<year>` | `view=proTeamSchedules_wl` | none |
| `players.json` | `/seasons/<year>/players` | `view=players_wl` | `{"filterActive":{"value":true}}` |
| `player_pool.json` | league route | `view=kona_player_info`, `scoringPeriodId=0` | `{"players":{"limit":2000,"sortPercOwned":{...}}}` |
| `boxscore_wNN.json` | league route | `view=[mMatchupScore,mScoreboard]`, `scoringPeriodId=NN` | `{"schedule":{"filterMatchupPeriodIds":{"value":[<period of week NN>]}}}` |
| `roster_wNN.json` | league route | `view=mRoster`, `scoringPeriodId=NN` | none |
| `transactions_wNN.json` | league route | `view=mTransactions2`, `scoringPeriodId=NN` | none (so all types come back) |
| `activity_pNNN` | league route + `/communication/` | `view=kona_league_communication` | topics filter, message types 178/179/180/181/239/244 |

The "league route" is `/seasons/<year>/segments/0/leagues/<leagueId>`, falling back to
`/leagueHistory/<leagueId>?seasonId=<year>` on HTTP 401. The library does the same fallback
[source: espn_api/requests/espn_requests.py@700e15d#L44-L90]. The box score call mirrors the
library's `box_scores()` [source: espn_api/football/league.py@700e15d#L359-L366]. Note the
library does not filter `mTransactions2` by default the way the archiver does not: the library
sends `filterType` = `FREEAGENT, WAIVER, WAIVER_ERROR` unless told otherwise
[source: espn_api/football/league.py@700e15d#L508-L537]. The archive is unfiltered, so it holds
every type.

Every league view repeats a common header: `id`, `seasonId`, `scoringPeriodId`, `segmentId`,
`gameId`, and usually `status` and `draftDetail.{drafted,inProgress}` [observed: all league_*
files, seasons 2018–2025].

---

## 1. Settings (`league_mSettings.json` → `core.seasons`)

| Path | Type | Meaning |
|---|---|---|
| `settings.size` | int | Team count. 10 in 2018–2019, 12 in 2020–2025 [observed: league_mSettings, 2018–2025]. |
| `settings.scheduleSettings.matchupPeriodCount` | int | **Regular-season** matchup periods. 13 (2018), 14 (2019–2025). Library calls it `reg_season_count` [source: espn_api/base_settings.py@700e15d#L8]. |
| `settings.scheduleSettings.matchupPeriods` | `{ "<periodId>": [scoringPeriodId, ...] }` | Matchup period → NFL weeks. 1:1 in 2019–2025. **2018 has two-week playoff periods**: period 14 = weeks 14–15, period 15 = weeks 16–17 [observed: league_mSettings, 2018]. Total periods: 15 (2018), 16 (2019), 17 (2020–2025). |
| `settings.scheduleSettings.playoffTeamCount` | int | 4 (2018–2019), 6 (2020–2025). |
| `settings.scheduleSettings.playoffMatchupPeriodLength` | int | Weeks per playoff period: 2 in 2018, 1 after. |
| `settings.scheduleSettings.playoffSeedingRule` | enum | Observed `TOTAL_POINTS_SCORED`. The library also knows `H2H_RECORD`, `INTRA_DIVISION_RECORD` [source: espn_api/football/league.py@700e15d#L186-L216]. |
| `settings.scheduleSettings.divisions[].{id,name,size}` | list | Divisions (2 every season). `name` is league data; do not publish. |
| `settings.scheduleSettings.playoffReseed`, `consolationLadderDisabled` | bool | Both `false` in every season. |
| `settings.scoringSettings.scoringType` | enum | `H2H_POINTS`. |
| `settings.scoringSettings.matchupTieRule` / `playoffMatchupTieRule` | enum | Values from ESPN's own list: `NONE, HOME_TEAM_WINS, SLOT_POINTS, STAT_POINTS, HIGHEST_PLAYOFF_SEED` [observed: pro_schedule `settings.typeNames.matchupTieRuleTypes`, 2025]. |
| `settings.scoringSettings.scoringItems[]` | list | One entry per scored stat (see below). |
| `settings.rosterSettings.lineupSlotCounts` | `{ "<lineupSlotId>": count }` | Starting/bench slots. Keys are **lineupSlotId** (§5). Non-zero in 2025: 0 QB ×1, 2 RB ×2, 4 WR ×2, 6 TE ×1, 23 FLEX ×2, 16 D/ST ×1, 17 K ×1, 20 BE ×7, 21 IR ×1. Earlier seasons differ: 2018–2020 FLEX ×1, BE ×7, no IR; 2021–2022 adds IR ×1; 2023–2024 FLEX ×2, BE ×8, IR ×1 [observed: league_mSettings, 2018–2025; corrected after the loader's export disagreed with the earlier note]. |
| `settings.rosterSettings.positionLimits` | `{ "<defaultPositionId>": max }` | Per-position roster caps. Keys are **defaultPositionId** (§5), not slot IDs. 2025 adds key `15` with `-1`. The library labels these keys with `ROSTER_POSITION_MAP` [source: espn_api/football/settings.py@700e15d#L15-L19]. |
| `settings.draftSettings.type` | enum | `OFFLINE` (2018), `SNAKE` (2019–2025). ESPN's list: `OFFLINE, SNAKE, AUTOPICK, SNAIL, AUCTION, LINEAR` [observed: pro_schedule `typeNames.draftTypes`]. |
| `settings.draftSettings.{keeperCount,auctionBudget,pickOrder[]}` | | `keeperCount` 0 every season. `pickOrder` = round-1 team order. |
| `settings.acquisitionSettings.isUsingAcquisitionBudget` | bool | FAAB on/off. `false` 2018–2024, `true` 2025. |
| `settings.acquisitionSettings.{acquisitionBudget,minimumBid,acquisitionType,waiverProcessDays,waiverHours}` | | Waiver/FAAB config. `acquisitionType` = `WAIVERS_TRADITIONAL`. |
| `settings.tradeSettings.{deadlineDate,vetoVotesRequired,revisionHours}` | | Trade deadline (epoch ms), veto votes needed, review window in hours. |
| `status.{firstScoringPeriod,finalScoringPeriod,latestScoringPeriod,currentMatchupPeriod}` | int | `finalScoringPeriod` = last fantasy week (17; 16 in 2019). `latestScoringPeriod` can exceed it (18–19) because the NFL season runs past the fantasy season. |
| `status.previousSeasons[]` | int[] | Prior seasons of this league. |

### Scoring items and per-position `pointsOverrides`

Each `scoringItems[]` entry: `statId` (int), `points` (float, the default), `pointsOverrides`
(optional `{ "<key>": points }`), `isReverseItem`, `leagueRanking`, `leagueTotal`.

**Override keys are `defaultPositionId` values, not lineup slots.** Evidence:

1. In 2025, statId 53 (each reception) has `points` 0 and `pointsOverrides`
   `{1:1, 2:1, 3:1, 4:1.5, 15:1}`. In every 2025 box score, receptions for players with
   `defaultPositionId` 4 are credited at 1.5 per catch, including when the player sits in the
   FLEX slot (23) or on the bench (20). Positions 1/2/3 are credited at 1.0. If the keys were
   lineup slots, key 4 would be the WR slot and a TE in FLEX would not get 1.5
   [observed: boxscore_wNN `appliedStats["53"] / stats["53"]`, 2025, 1,973 player-weeks].
2. ESPN's own `statIdToOverridePosition` maps D/ST stats (89–137, 206, 209) to `16` and head-coach
   stats (155–174) to `14`. Both are `defaultPositionId` values [observed: pro_schedule.json
   `settings.statIdToOverridePosition`, 2025].
3. The library reads key `"16"` as the D/ST override [source: espn_api/football/settings.py@700e15d#L23].

So the keys mean:

| Key | Position | Source |
|---|---|---|
| 1 | QB | ROSTER_POSITION_MAP [source: espn_api/football/constant.py@700e15d#L49] and data (eligible for slot 0 QB) |
| 2 | RB | constant.py@700e15d#L50 and data |
| 3 | WR | constant.py@700e15d#L51 and data |
| 4 | TE | constant.py@700e15d#L52 and the 1.5× reception check above |
| 15 | TQB (team quarterback, one per NFL team) | constant.py@700e15d#L63. Data: all 32 players with `defaultPositionId` 15 are eligible only for slot 1 (`TQB`) plus BE/IR [observed: players.json, 2025]. No TQB was rostered, so the key-15 override was never exercised. |
| 16 | D/ST | constant.py@700e15d#L64, settings.py@700e15d#L23, `statIdToOverridePosition` |

Rule for the loader: the points for stat *s* and a player at position *p* are
`pointsOverrides[str(p)]` if present, else `points`. Only 2025 has overrides on offensive stats
(42, 43, 44, 53); 2018–2024 have only key `16` [observed: league_mSettings, 2018–2025].

**Gotcha.** The box score files carry `settings.scoringSettings.scoringItems[]` too, but
**without `pointsOverrides`** [observed: boxscore_wNN, 2025]. Always take scoring rules from
`league_mSettings.json`.

**Library limitation.** `Settings.scoring_format` keeps only the `"16"` override and ignores all
other keys [source: espn_api/football/settings.py@700e15d#L21-L29]. Do not copy that logic.

You rarely need to recompute points: ESPN stores the applied values (§4). Use the rules to
validate or to explain.

---

## 2. Teams, standings, members (`league_mTeam.json` → `core.franchises`)

| Path | Meaning |
|---|---|
| `teams[].id` | Team ID within the season (int). Not a person. |
| `teams[].owners[]` | Member IDs (strings in `{GUID}` form). Exactly 1 owner per team every season. |
| `teams[].primaryOwner` | Member ID; always one of `owners[]`. |
| `members[].{id,displayName,firstName,lastName}` | The member table. Every `owners[]` value is in `members[].id` [observed: league_mTeam, 2018–2025]. The library joins the same way [source: espn_api/base_league.py@700e15d#L118-L124]. This is personal data: archive only, never publish. Per ADR 0005, owners are mapped by hand. |
| `teams[].divisionId` | Division ID. |
| `teams[].record.overall.{wins,losses,ties,pointsFor,pointsAgainst,percentage,gamesBack,streakLength,streakType}` | **Regular season only.** In 2019–2025, wins/losses/PF recomputed from regular-season matchups match exactly. In 2018 they also match once the `adjustment` values (§3) are added to PF [observed: league_mTeam vs league_mMatchupScore, 2018–2025]. `record.home`, `record.away`, `record.division` have the same shape. |
| `teams[].playoffSeed` | Seed at the end of the regular season (1..size). Library calls it `standing` [source: espn_api/football/team.py@700e15d#L37]. |
| `teams[].rankCalculatedFinal` | **Final placement (1 = champion).** Matches the bracket results in every season (§3). |
| `teams[].rankFinal` | **Always 0** in every season [observed: league_mTeam, 2018–2025]. The library uses `rankFinal or rankCalculatedFinal` [source: espn_api/football/team.py@700e15d#L38], so in practice it also falls through to `rankCalculatedFinal`. Inferred: `rankFinal` is a manual override that this league never set. |
| `teams[].points` | **Do not use.** Equals regular-season PF in 2019–2025 but not in 2018 (it includes playoffs there). |
| `teams[].transactionCounter.{acquisitions,drops,trades,acquisitionBudgetSpent,moveToIR}` | Season counters. `trades` counts each trade once per side (sum/2 = trade count; reconciles with §7 every season). `acquisitionBudgetSpent` equals the sum of `bidAmount` over the team's EXECUTED WAIVER rows (12/12 teams, 2025). `acquisitions` does **not** always reconcile with ADD items (2022, 2025). |
| `teams[].valuesByStat` | Team stat totals keyed by statId. **Missing in 2018.** |
| `teams[].name`, `abbrev`, `logo` | League data. Archive only. |

`league_mStandings.json` is a lighter copy: `teams[]` and `schedule[]` with only
`{home,away}.{teamId,totalPoints,gamesPlayed}` and `matchupPeriodId`. Use `mTeam` and
`mMatchupScore` instead.

---

## 3. Matchups (`league_mMatchupScore.json` → `core.matchups`)

`schedule[]` holds every matchup of the season (2025: 103 entries) [observed: league_mMatchupScore, 2018–2025].

| Path | Meaning |
|---|---|
| `schedule[].id` | Matchup ID, unique within a season. |
| `schedule[].matchupPeriodId` | Matchup period (not NFL week; see `matchupPeriods`). |
| `schedule[].home.teamId` / `away.teamId` | Teams. **`away` is absent for a playoff bye**: 2 per season in 2020–2025 (seeds 1 and 2 in the first playoff round). |
| `schedule[].{home,away}.totalPoints` | Matchup total. Equals the sum of `pointsByScoringPeriod` in every matchup checked. |
| `schedule[].{home,away}.pointsByScoringPeriod` | `{ "<week>": points }`. One key normally, two for 2018's two-week playoff periods. |
| `schedule[].{home,away}.adjustment` | Manual score adjustment. Non-zero twice (2018). It is **not** in `totalPoints` but **is** in `record.overall.pointsFor` [observed: 2018]. `winner` followed `totalPoints` in both cases. Store it as its own column. |
| `schedule[].{home,away}.totalPointsLive` | Present only in the final matchup period of a season, and equal to `totalPoints` there. The library prefers it when present [source: espn_api/football/box_score.py@700e15d#L78-L82]. Safe to ignore for completed seasons. |
| `schedule[].winner` | `HOME`, `AWAY`, `TIE`, `UNDECIDED` [observed: pro_schedule `typeNames.winnerTypes`]. Byes are `UNDECIDED`. No ties observed. `winner` always matches the higher `totalPoints`. |
| `schedule[].playoffTierType` | `NONE` (regular season), `WINNERS_BRACKET`, `WINNERS_CONSOLATION_LADDER`, `LOSERS_CONSOLATION_LADDER`. The library only uses it as `is_playoff = type != "NONE"` [source: espn_api/football/matchup.py@700e15d#L8-L9]. |

### What the tiers mean (observed shape, 12 teams / 6 playoff teams, 2020–2025)

- Periods 1–14: `NONE`, 6 games each.
- Period 15: `WINNERS_BRACKET` ×4 (3v6, 4v5, and byes for 1 and 2) + `LOSERS_CONSOLATION_LADDER` ×3 (seeds 7–12).
- Period 16: `WINNERS_BRACKET` ×2 (semifinals) + `WINNERS_CONSOLATION_LADDER` ×1 (round-1 losers) + `LOSERS_CONSOLATION_LADDER` ×3.
- Period 17: `WINNERS_BRACKET` ×1 (final) + `WINNERS_CONSOLATION_LADDER` ×2 (3rd-place game, 5th-place game) + `LOSERS_CONSOLATION_LADDER` ×3.

2018 (10 teams, 4 playoff teams, 2-week rounds) and 2019 (10 teams, 4 playoff teams) have no
byes and one `WINNERS_CONSOLATION_LADDER` game (the 3rd-place game) [observed: league_mMatchupScore, 2018–2025].

### Identifying the championship and the 3rd-place game

- **Championship:** the single `WINNERS_BRACKET` matchup in the last matchup period
  (`max(matchupPeriodId)`). Its winner has `rankCalculatedFinal = 1` in every season
  [observed: 2018–2025].
- **3rd-place game:** the `WINNERS_CONSOLATION_LADDER` matchup in the last period **whose two teams
  are the losers of the previous `WINNERS_BRACKET` round** (the semifinals). Its winner has
  `rankCalculatedFinal = 3` in every season [observed: 2018–2025]. Tier type alone is not
  enough: from 2020 the last period also has a `WINNERS_CONSOLATION_LADDER` 5th-place game.
- In 2020–2025 the round-1 losers also meet in period 16 under `WINNERS_CONSOLATION_LADDER`, then
  again in period 17. **Inferred:** ESPN schedules a consolation game every week for eliminated
  teams; only the final-period game sets the placement. Use `rankCalculatedFinal` as the
  authority for final places and the rule above only to label games.

---

## 4. Box scores and lineups (`boxscore_wNN.json` → `core.lineup_entries`, `core.player_week_stats`)

With the matchup-period filter, `schedule[]` holds only that period's matchups (2025 week 1: 6).
In 2018's two-week periods, `boxscore_w14` and `boxscore_w15` both return period 14, but each
file's lineup and stats are for its own `scoringPeriodId` [observed: boxscore_w14/w15, 2018].

Per side (`schedule[].home` / `.away`), on top of the §3 fields:

| Path | Meaning |
|---|---|
| `rosterForCurrentScoringPeriod.entries[]` | **The lineup for week NN**: every rostered player, starters and bench. Use this one. |
| `rosterForCurrentScoringPeriod.appliedStatTotal` | Equals the team's score for week NN. |
| `rosterForMatchupPeriod.entries[]` | **Do not use for lineups.** Only scoring players, every `lineupSlotId` = 0, and stats carry `scoringPeriodId` 0 with id `"01null"` [observed: 2018, 2025]. |
| `cumulativeScore.scoreByStat` | Per-stat team totals. Not needed. |

Each `entries[]` item:

| Path | Meaning |
|---|---|
| `lineupSlotId` | Slot this week (§5). Starters = any slot except 20 (BE) and 21 (IR). |
| `playerId` | ESPN player ID (same as `playerPoolEntry.player.id`). |
| `playerPoolEntry.onTeamId` | Fantasy team holding the player. |
| `playerPoolEntry.appliedStatTotal` | The player's actual fantasy points for week NN. Equals the actual stat row's `appliedTotal` in every entry checked. |
| `playerPoolEntry.player.{defaultPositionId,eligibleSlots[],proTeamId,injuryStatus,fullName}` | Player info. `proTeamId` here is the player's **current** NFL team. For the team in that game, use `stats[].proTeamId` on the actual row; the library does the same [source: espn_api/football/box_player.py@700e15d#L34-L51]. |
| `playerPoolEntry.player.stats[]` | Two rows per entry: actual and projection (see below). |

**Check that the lineup is real:** the sum of starters' actual `appliedTotal` equals
`pointsByScoringPeriod[NN]` for every team-week in 2018 and 2020–2025 (2025: 204/204; 2018: 170/170)
[observed: boxscore_wNN vs league_mMatchupScore].

### Player stat rows (`player.stats[]`)

| Field | Meaning |
|---|---|
| `statSourceId` | `0` = actual, `1` = projection. Library: [source: espn_api/football/player.py@700e15d#L86-L96]. |
| `statSplitTypeId` | `1` = single scoring period; `0` = season total (`scoringPeriodId` 0); `2` = only on projections with `scoringPeriodId` 0. The library skips split 2 [source: espn_api/football/player.py@700e15d#L69]. Inferred: split 2 is a rest-of-season projection. 2018 roster data also shows split 3 on projections. |
| `scoringPeriodId` | NFL week, or 0 for season rows. |
| `seasonId` | Season. |
| `stats` | `{ "<statId>": raw value }`: yards, receptions, etc. |
| `appliedStats` | `{ "<statId>": fantasy points }`. Only stats the league scores. Position overrides are already applied. |
| `appliedTotal` | Fantasy points; equals the sum of `appliedStats` (2025: 3,391/3,391 actual rows). |
| `proTeamId` | NFL team for that game. |
| `externalId`, `id` | Actual weekly rows: `id = "01" + externalId`, `externalId` = ESPN game ID. Projection rows: `id = "11" + season + week`. |

For `core.player_week_stats`, take `statSourceId=0, statSplitTypeId=1, scoringPeriodId=NN`. Store
projections (`statSourceId=1`) separately if wanted. The library's projected team score is the sum
of starters' projections when `totalProjectedPointsLive` is absent
[source: espn_api/football/box_score.py@700e15d#L54-L61].

Coverage: box scores contain **rostered players only**. `player_pool.json`
(`scoringPeriodId=0`) holds season totals for about 1,100 players but only one weekly row each,
so it is not a weekly source for free agents [observed: player_pool, 2018–2025].

### Weekly rosters (`roster_wNN.json`)

`teams[].roster.entries[]`, the same entry shape as box scores plus `acquisitionType`,
`acquisitionDate`, `playerPoolEntry.keeperValue`, `player.ownership`. Each entry carries actual
and projected rows for weeks NN and NN−1, so consecutive files overlap. Dedupe on
`(playerId, seasonId, scoringPeriodId, statSourceId, statSplitTypeId)`. Lineups differ week to
week in 2018 and 2020–2025 (17 distinct per season). Use these files for roster-diff checks on
trades (§7).

The season-level `league_mRoster.json` is the end-of-season roster. Its
`entries[].acquisitionType` (`DRAFT` / `ADD` / `TRADE`) shows how each final-roster player was
acquired (null in 2019).

---

## 5. Enums

### `lineupSlotId` (slot a player occupies)

Source: `POSITION_MAP` [source: espn_api/football/constant.py@700e15d#L1-L27].

| ID | Slot | ID | Slot | ID | Slot |
|---|---|---|---|---|---|
| 0 | QB | 9 | DE | 18 | P |
| 1 | TQB | 10 | LB | 19 | HC |
| 2 | RB | 11 | DL | 20 | BE (bench) |
| 3 | RB/WR | 12 | CB | 21 | IR |
| 4 | WR | 13 | S | 22 | (unused) |
| 5 | WR/TE | 14 | DB | 23 | FLEX (RB/WR/TE) |
| 6 | TE | 15 | DP | 24 | ER |
| 7 | OP (superflex) | 16 | D/ST | 25 | Rookie |
| 8 | DT | 17 | K | | |

Spot check: lineups used only 0, 2, 4, 6, 16, 17, 20, 21, 23, matching `lineupSlotCounts`
[observed: boxscore_wNN, 2025]. Draft picks also show `lineupSlotId` −1 (2018 only, see §6).

### `defaultPositionId` (a player's position)

Source: `ROSTER_POSITION_MAP` [source: espn_api/football/constant.py@700e15d#L46-L66]. The library
has a TODO for IDs 0, 6, 8, 17 (L47). **Do not use `POSITION_MAP` for this field**: the two
spaces differ (4 = WR slot but 4 = TE position).

| ID | Position | Data check: slots every player at this position is eligible for [observed: players.json, 2025] |
|---|---|---|
| 1 | QB | 0, 7, 20, 21 |
| 2 | RB | 2, 3, 7, 20, 21, 23 |
| 3 | WR | 3, 4, 5, 7, 20, 21, 23 |
| 4 | TE | 5, 6, 7, 20, 21, 23 |
| 5 | K | 17, 20, 21 |
| 7 | P | 18, 20, 21 |
| 9 | DT | 8, 11, 15, 20, 21 |
| 10 | DE | 9, 11, 15, 20, 21 |
| 11 | LB | 10, 15, 20, 21 |
| 12 | CB | 12, 14, 15, 20, 21 |
| 13 | S | 13, 14, 15, 20, 21 |
| 14 | HC | 19, 20, 21 |
| 15 | TQB | 1, 20, 21 |
| 16 | D/ST | 16, 20, 21 |

All 14 rows agree with the library. Only 1, 2, 3, 4, 5, 16 appear on fantasy rosters (plus a few
7/9/12 in the pool).

### `proTeamId`

Source: `PRO_TEAM_MAP` [source: espn_api/football/constant.py@700e15d#L68-L102]. Matches
`pro_schedule.json settings.proTeams[].{id,abbrev}` for all 33 IDs (data uses mixed-case
abbreviations; `0` = `FA`) [observed: pro_schedule, 2025]:

0 FA, 1 ATL, 2 BUF, 3 CHI, 4 CIN, 5 CLE, 6 DAL, 7 DEN, 8 DET, 9 GB, 10 TEN, 11 IND, 12 KC, 13 LV,
14 LAR, 15 MIA, 16 MIN, 17 NE, 18 NO, 19 NYG, 20 NYJ, 21 PHI, 22 ARI, 23 PIT, 24 LAC, 25 SF,
26 SEA, 27 TB, 28 WSH, 29 CAR, 30 JAX, 33 BAL, 34 HOU. (31, 32 unused.)

`pro_schedule.json` also gives `proTeams[].byeWeek` and
`proGamesByScoringPeriod["<week>"][].{id,homeProTeamId,awayProTeamId,date}`. The game `id` equals
the stat row `externalId`.

### `statId`

Two maps in the library: `PLAYER_STATS_MAP` (raw stat names) [source:
espn_api/football/constant.py@700e15d#L116-L275] and `SETTINGS_SCORING_FORMAT_MAP` (scoring
labels) [source: espn_api/football/constant.py@700e15d#L277-L513]. Use the second for scoring
items. Ones this league scores (2025 `scoringItems`):

| statId | Meaning | statId | Meaning |
|---|---|---|---|
| 3 | Passing yards | 77 / 80 / 198 / 201 | FG made 40–49 / 0–39 / 50–59 / 60+ |
| 4 | TD pass | 85 | FG missed |
| 19 / 26 / 44 | 2-pt pass / rush / rec | 86 | PAT made |
| 20 | Interception thrown | 89–92, 121, 123–125 | D/ST points-allowed buckets |
| 24 | Rushing yards | 93 | Blocked kick return TD |
| 25 | TD rush | 95–99 | D/ST INT, fumble rec, blocked kick, safety, sack |
| 42 | Receiving yards | 101–104 | Kick/punt/INT/fumble return TD |
| 43 | TD reception | 128–130, 132–136 | D/ST yards-allowed buckets |
| 53 | Each reception | 206 / 209 | 2-pt return / 1-pt safety |
| 63 | Fumble recovered for TD | 72 | Fumbles lost |

2018–2019 also scored 74 (FG 50+) instead of 198/201 [observed: league_mSettings]. **Spot check:**
raw `stats` carries both 41 and 53 with equal values, plus 58 (targets) [observed: boxscore_w03,
2025]; the library's TODO asking how 41 and 53 differ (L161) does not matter here, because the
league scores 53.

### Other ESPN enums

`pro_schedule.json settings.typeNames` lists ESPN's own enum names: `transactionTypes`,
`transactionStatusTypes` (33 values, index 0 = `FAILED_UNKNOWN`, 1 = `PENDING`, 2 = `EXECUTED`,
3 = `CANCELED`, …), `moveTypes` (`LINEUP, ADD, DROP, TRADE, DRAFT, …`), `playoffTierTypes`,
`winnerTypes`, `draftTypes`, `transactionTeamActionTypes`
(`INVOLVED, ACCEPTED, APPROVED, VETOED, PROTESTED`), `rosterStatusTypes` [observed: pro_schedule,
2025]. Treat it as the canonical value list. `typeNames.messageTypes` list positions do **not**
match `messageTypeId` (index 178 is a settings message, not "FA added"), so it cannot decode the
activity feed.

---

## 6. Draft (`league_mDraftDetail.json` → `core.draft_picks`)

| Path | Meaning |
|---|---|
| `draftDetail.drafted`, `completeDate` | Draft done; epoch ms. |
| `draftDetail.picks[].overallPickNumber` | 1..N; equals array order in every season. |
| `picks[].roundId`, `roundPickNumber` | Round and pick within round. |
| `picks[].teamId`, `playerId` | Drafting team, player. |
| `picks[].bidAmount` | Auction price; 0 in every season (no auction drafts). Library reads it as `bid_amount` [source: espn_api/base_league.py@700e15d#L81-L103]. |
| `picks[].nominatingTeamId` | Auction nominator; 0 here. |
| `picks[].keeper`, `reservedForKeeper` | Keeper flags; all `false` (`keeperCount` 0). |
| `picks[].autoDraftTypeId` | 0 on most picks, 1/2/3 on some. `memberId` is present only on picks with `autoDraftTypeId` 0. **Inferred:** non-zero = auto-picked; the exact 1/2/3 meanings are unknown. |
| `picks[].memberId` | Member who made the pick. Personal: do not publish. |
| `picks[].lineupSlotId` | Slot the pick was placed in. |
| `picks[].tradeLocked` | All `false`. |

Snake check: round 2 is the reverse of round 1 and `pickOrder` equals round 1 in every season,
including 2018's `OFFLINE` draft [observed: 2018–2025]. Picks per season: 160 (2018–2019),
192 (2020–2022), 216 (2023–2024), 204 (2025).

Auction vs snake: use `settings.draftSettings.type`; for an auction, `bidAmount` holds the price.

`mTransactions2` also has one `DRAFT` row per pick in week 1 (item type `DRAFT`, `fromTeamId` 0).
In 2018 there are 147 rows for 160 picks; the 13 missing picks are exactly the picks with
`lineupSlotId` −1, and all 2018 `DRAFT` rows have status `PENDING`. **Use `draftDetail.picks` as
the source of truth.**

---

## 7. Transactions (`transactions_wNN.json` → `core.transactions`, `core.transaction_items`)

### Shape

`transactions[]` per file. No ID appears in more than one weekly file, and every row's
`scoringPeriodId` equals the file's week, so **weeks do not duplicate** [observed: 2018,
2020–2025]. Each row is a transaction for that scoring period.

| Field | Meaning |
|---|---|
| `id` | UUID string. |
| `type` | `DRAFT, FREEAGENT, WAIVER, ROSTER, FUTURE_ROSTER, TRADE_PROPOSAL, TRADE_ACCEPT, TRADE_DECLINE, TRADE_UPHOLD, TRADE_VETO`. Library list also has `RETRO_ROSTER, WAIVER_ERROR, TRADE_ERROR` [source: espn_api/football/constant.py@700e15d#L515-L529]; not observed. |
| `status` | `EXECUTED, CANCELED, PENDING, FAILED_*`. **Missing on most `TRADE_ACCEPT` rows (2020–2025).** |
| `executionType` | `EXECUTE`, `PROCESS`, `CANCEL`. Needed to read 2018 (below). |
| `isPending` | bool. |
| `teamId` | Team that made the transaction (see the 2018 waiver note). |
| `memberId` | Acting member. Personal. |
| `isLeagueManager` | Action taken by the commissioner. |
| `bidAmount` | FAAB bid (int). |
| `proposedDate` | Epoch ms; on every row. |
| `processDate` | On processed waivers and on processed trades. |
| `acceptedDate`, `expirationDate`, `teamActions` | Trade fields; `teamActions` = `{ "<teamId>": "ACCEPTED" \| "INVOLVED" ... }`. |
| `relatedTransactionId` | Links trade rows (below). |
| `items[]` | `{type, playerId, fromTeamId, toTeamId, fromLineupSlotId, toLineupSlotId, isKeeper, overallPickNumber}`. |

Item types: `ADD` (`fromTeamId` 0 = player pool), `DROP` (`toTeamId` 0), `TRADE` (both team IDs
> 0), `DRAFT`, `LINEUP` (both team IDs 0; slot move) [observed: 2018, 2020–2025]. The library
models items the same way [source: espn_api/football/transaction.py@700e15d#L27-L33].

### Telling a waiver claim, a free-agent add, and a drop apart

| What happened | Row | Executed when |
|---|---|---|
| Waiver claim | `type = WAIVER`, items `ADD` (+ optional `DROP`) | `status = EXECUTED` (`executionType = PROCESS`, has `processDate`) |
| Free-agent add (no waiver) | `type = FREEAGENT`, items `ADD` (+ optional `DROP`) | `status = EXECUTED` |
| Standalone drop | 2020–2025: `type = ROSTER` with a `DROP` item. 2018: `type = FREEAGENT` with only a `DROP` item. | `status = EXECUTED` |
| Lineup change | `ROSTER` / `FUTURE_ROSTER` with `LINEUP` items | Not needed for core; real lineups come from §4. |

Statuses that are **not** executed moves:
- `WAIVER` + `CANCELED` (withdrawn), `FAILED_INVALIDPLAYERSOURCE` (another team won the player;
  the library labels it "Outbid" [source: espn_api/base_offer.py@700e15d#L21-L22]),
  `FAILED_PLAYERALREADYDROPPED`, `FAILED_ROSTERLIMIT`, `FAILED_POSITIONLIMIT`, `FAILED_IRSLOT`,
  `FAILED_MATCHUPACQUISITIONLIMIT`, `FAILED_AUCTIONBUDGETEXCEEDED`, `FAILED_TRADE_RESERVED`.
- `WAIVER` + `PENDING` (`executionType EXECUTE`, `isPending true`): 27–44 per season. These never
  processed. The library also treats `PENDING` as not processed
  [source: espn_api/base_offer.py@700e15d#L29-L37]. Roster diffs show the player on the claimant's
  roster the next week in about half of them, so **Inferred:** the player arrived through another
  transaction. Do not count `PENDING` rows as moves.

**2018 uses different statuses.** Cancelled waivers are `status PENDING` + `executionType CANCEL`
(no `CANCELED` status), `DRAFT` rows are `PENDING`, and `TRADE_ACCEPT` rows are `PENDING` +
`PROCESS`. In 2018, 295 of 445 `WAIVER` rows have a top-level `teamId` that differs from the ADD
item's `toTeamId`; roster diffs follow `items[].toTeamId` [observed: transactions_wNN + roster_wNN,
2018]. **Rule: take the receiving team from `items[].toTeamId`, never from top-level `teamId`.**

### FAAB `bidAmount`

FAAB only applies in 2025 (`isUsingAcquisitionBudget`). In 2018–2024 every `bidAmount` is 0. In
2025, EXECUTED, PENDING and FAILED waivers carry bids; CANCELED rows show 0. Per-team
`transactionCounter.acquisitionBudgetSpent` equals the sum of `bidAmount` over **EXECUTED WAIVER**
rows only (12/12 teams). Two 2025 `FREEAGENT` rows carry a non-zero `bidAmount` that is **not**
charged; ignore `bidAmount` on `FREEAGENT` rows [observed: 2025].

### Trades: which records mean "a trade executed"

**2020–2025 (the main case).**

- An accepted trade shows up as a `TRADE_ACCEPT` row. All rows of one trade share
  `relatedTransactionId` = the ID of the original `TRADE_PROPOSAL`: the `TRADE_ACCEPT`, every
  `TRADE_UPHOLD`, any `TRADE_VETO`, and sometimes a second `TRADE_ACCEPT` [observed: 2020–2025].
  **Count trades as distinct `relatedTransactionId` values among `TRADE_ACCEPT` rows.**
- **The accepted proposal itself is almost never in the archive** (`relatedTransactionId` points
  to an ID absent from every weekly file). `TRADE_PROPOSAL` rows that *are* present are
  `CANCELED` or `PENDING` proposals that never completed, sometimes chained to each other
  (counter-offers) through `relatedTransactionId`.
- **`TRADE_ACCEPT` usually has no `TRADE` legs** (empty `items`, or only the acceptor's `DROP`s)
  and no `status`. The full legs appear only on a second `TRADE_ACCEPT` row
  (`status EXECUTED`, `executionType PROCESS`, `processDate`, `acceptedDate`, `TRADE` items),
  which exists for 1 trade in each of 2020, 2022 and 2024. This matches the library's note that
  `mTransactions2` leaves out the player lists on other teams' trades
  [source: espn_api/football/league.py@700e15d#L518-L523; espn_api/base_league.py@700e15d#L283].
  **Inferred:** full legs show only for trades the cookie owner was part of.
- `TRADE_UPHOLD` = a team (or the commissioner, `isLeagueManager true`) approving during review.
  `TRADE_VETO` = a veto. `TRADE_DECLINE` = a recipient declining (linked to proposals not in the
  archive).
- **Veto outcome:** a `TRADE_VETO` with `isLeagueManager true` killed the trade (2020: no
  players moved, and `transactionCounter.trades` excludes it). A non-commissioner veto below
  `vetoVotesRequired` did not stop the trade (2020, 2022, 2023).
- **Check:** distinct accepted trades minus commissioner-vetoed ones equals
  `sum(transactionCounter.trades)/2` every season: 10, 4, 8, 4, 5, 4 for 2020–2025.
- **Timing:** players appear on their new team in `roster_w(N)` or `roster_w(N+1)`, where N is the
  `TRADE_ACCEPT.scoringPeriodId` (review window `revisionHours` = 24; a commissioner uphold makes
  it immediate). Week-1 trades happen before the first roster snapshot.

**How the loader recovers trade legs (2020–2025):** for each executed trade (one
`relatedTransactionId`), the legs are the players who move between the two teams' rosters from
`roster_w(N-1)` to `roster_w(N)` or `roster_w(N+1)` **without** a matching executed ADD. Use the
`TRADE_ACCEPT.teamId` and its `teamActions` keys (when present) for the two sides. The roster-diff
check found one team pair per trade in every week checked. Other ways to get legs: the end-of-season
`acquisitionType = TRADE` on `league_mRoster.json`, or the library's player-card fill
(`kona_playercard`, `fill_trade_items=True`) [source: espn_api/base_league.py@700e15d#L273-L317;
espn_api/utils/trade_fill.py@700e15d#L44-L103]. The archive has no player-card calls.

**2018 is different and easier.** No row has `relatedTransactionId`. Every `TRADE_ACCEPT` carries
full `TRADE` legs, `acceptedDate`, and `processDate = acceptedDate + 48 h`. Each one matches
exactly one `TRADE_UPHOLD` and one `TRADE_PROPOSAL` with the same legs, and the legs show up on the
new rosters in week N or N+1. 6 `TRADE_ACCEPT` rows = 6 trades = `transactionCounter.trades`/2.
All 372 2018 `TRADE_PROPOSAL` rows have `status PENDING`, so **proposal rows are not evidence of
a trade in 2018 either** [observed: 2018]. **Rule for 2018:** one executed trade per
`TRADE_ACCEPT` row, with legs from its own `items`.

---

## 8. Activity feed (`/communication/`, `kona_league_communication`)

Returned HTTP 404 "This Communication Group does not exist" for **every** season, 2018–2025
[observed: manifest.jsonl]. The library expects this: "Historical leagues often 404 on
/communication/" and it returns no topics [source: espn_api/requests/espn_requests.py@700e15d#L92-L98].

What the feed would have added: one message per add/drop/trade with message types 178 FA added,
180 waiver added, 179/181/239 dropped, 244 traded [source: espn_api/football/constant.py@700e15d#L104-L114],
including the `from`/`to` team for each traded player [source: espn_api/football/activity.py@700e15d#L12-L35].

What the loader loses without it: **only an easy source of trade legs for 2020–2025** (the
`TRADE_ACCEPT` legs are empty there). Adds, drops, waivers, FAAB and draft are complete in
`mTransactions2`, and trade legs can be rebuilt from weekly rosters (§7). 2018 loses nothing.

---

## 9. Year differences

| Topic | 2018 | 2019 (leagueHistory route) | 2020–2024 | 2025 |
|---|---|---|---|---|
| Teams / playoff teams | 10 / 4 | 10 / 4 | 12 / 6 | 12 / 6 |
| Regular-season periods / total periods | 13 / 15 | 14 / 16 | 14 / 17 | 14 / 17 |
| Playoff period length | 2 weeks (periods 14, 15) | 1 | 1 | 1 |
| Final fantasy week | 17 | 16 | 17 | 17 |
| Playoff byes (`away` missing) | 0 | 0 | 2 | 2 |
| Draft type | `OFFLINE` (snake order) | `SNAKE` | `SNAKE` | `SNAKE` |
| Lineup slots | FLEX ×1, no IR | FLEX ×1, no IR | FLEX ×1, no IR (2020); IR ×1 from 2021; FLEX ×2, BE ×8 from 2023 | FLEX ×2, BE ×7, IR ×1 |
| Offensive `pointsOverrides` (TE premium) | none | none | none | keys 1/2/3/4/15 |
| FAAB | off | off | off | on |
| `teams[].valuesByStat` | missing | present | present | present |
| `teams[].points` = PF | no | yes | yes | yes |
| Box score lineups | yes | **no** | yes | yes |
| Weekly rosters vary by week | yes | **no (same file every week)** | yes | yes |
| `mTransactions2` | yes, 2018 status rules | **empty** | yes | yes |
| Trade legs on `TRADE_ACCEPT` | yes | n/a | mostly empty | empty |
| `relatedTransactionId` | absent | n/a | present | present |
| Standalone drop type | `FREEAGENT` (DROP only) | n/a | `ROSTER` | `ROSTER` |
| End-of-season `acquisitionType` | present | null | present | present |
| Activity feed | 404 | 404 | 404 | 404 |

The library refuses box scores, recent activity and free agents for seasons before 2019
[source: espn_api/football/league.py@700e15d#L281, #L348, #L421]. **The data disagrees for this
league:** 2018 on the `/seasons/` route returns full box scores, lineups and transactions. The
library also switches to `leagueHistory` for seasons before 2018
[source: espn_api/requests/espn_requests.py@700e15d#L46-L53]; 2018 did not need it.

Note: `scripts/archive_espn.py` still sets `FULL_DATA_FROM = 2019`, which skips per-week calls for
2018. The 2018 per-week files in the archive came from a re-run with per-week calls enabled.

### 2019 and the leagueHistory route

`/seasons/2019/...` returned 401 because the cookie owner was not a league member in 2019, so the
archiver fell back to `/leagueHistory/<leagueId>?seasonId=2019` (all 57 league calls) [observed:
manifest.jsonl, 2019]. On that route:

- League-level views (`mSettings`, `mTeam`, `mMatchupScore`, `mStandings`, `mDraftDetail`,
  `mRoster`) have full data, so seasons, franchises, matchups, standings and draft load normally.
- `boxscore_wNN.json` matchups have no `rosterForCurrentScoringPeriod` or `rosterForMatchupPeriod`:
  no lineups.
- All 16 `roster_wNN.json` files have the same rosters and slots (the end-of-season roster). The
  weekly stat rows are real, but only for players on the final rosters, and the slots are not that
  week's lineup.
- `transactions_wNN.json` has no `transactions` key at all. Yet `transactionCounter.trades`/2 = 13
  shows trades happened.
- `league_mRoster.json` `acquisitionType` is null.

**Inferred:** these are limits of the `leagueHistory` route, not of 2019. Refetch 2019 on the
`/seasons/` route with a 2019 member's cookies, then re-run this analysis for 2019.

---

## Loader checklist

1. Scoring rules from `league_mSettings`; overrides keyed by `defaultPositionId`.
2. Matchups from `league_mMatchupScore`. Handle a missing `away` (bye). Store `adjustment` separately.
3. Final placement from `rankCalculatedFinal`; ignore `rankFinal` and `teams[].points`.
4. Lineups and player-week stats from `boxscore_wNN.rosterForCurrentScoringPeriod`; actual = `statSourceId 0, statSplitTypeId 1`.
5. Draft from `draftDetail.picks`, not `DRAFT` transaction rows.
6. Moves: only `status EXECUTED`; team from `items[].toTeamId`; 2018 status quirks.
7. Trades: one per `relatedTransactionId` on `TRADE_ACCEPT` (2020+) or one per `TRADE_ACCEPT` (2018); drop commissioner-vetoed ones; rebuild 2020+ legs from roster diffs; reconcile with `transactionCounter.trades`/2.
8. Skip 2019 per-week data until it is refetched.

## Open questions (need someone who remembers league events)

1. **Trade list.** For each season, check the trade count (2018: 6, 2019: 13 per counters, 2020: 10,
   2021: 4, 2022: 8, 2023: 4, 2024: 5, 2025: 4) and the weeks the loader assigns against the trades
   you remember. Confirm the 2020 commissioner veto (week 12) really cancelled a trade.
2. **Roster-diff legs.** After the loader rebuilds 2020–2025 trade legs from roster diffs, check a
   few against memory, especially weeks with several trades (2022 week 9 had four).
3. **2018 score adjustments.** Two manual adjustments in matchup period 4 count toward PF but did not
   change the winner. Confirm they were intended commissioner corrections.
4. **2018 waiver `teamId`.** Why does the top-level `teamId` differ from the ADD target on most 2018
   waiver rows? The loader ignores it, but confirm 2018 waiver pickups landed on the teams the items
   say.
5. **5th-place games.** From 2020, round-1 losers play in both periods 16 and 17. Confirm the league
   treats only the final week as the 5th-place game (`rankCalculatedFinal` agrees with that reading).
6. **2019.** Who was in the league in 2019 and can supply cookies for a `/seasons/2019` refetch?
7. **`autoDraftTypeId` 1/2/3.** Were those picks auto-drafted (absent owner, timer)? It only matters
   if the site will flag auto-picks.
