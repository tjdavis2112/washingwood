-- Washingwood league history schema (PostgreSQL 16)
--
-- Three layers:
--   raw.*   : untouched platform responses. Source of truth; never edited.
--   core.*  : platform-neutral model. Rebuilt from raw by the normalizer.
--   stats.* : derived views. Rebuilt any time a formula changes.
--
-- Platform-specific IDs never act as primary keys in core. They live in
-- *_external_ids tables so a switch from ESPN to Sleeper/Yahoo only adds rows.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS stats;

-- ---------------------------------------------------------------------------
-- RAW
-- ---------------------------------------------------------------------------

CREATE TABLE raw.responses (
    response_id     bigserial PRIMARY KEY,
    platform        text        NOT NULL,             -- 'espn', 'sleeper', ...
    league_ext_id   text        NOT NULL,
    season          int         NOT NULL,
    resource        text        NOT NULL,             -- e.g. 'league:mSettings', 'boxscore'
    scoring_period  int,                              -- NFL week, when the call is per-week
    url             text        NOT NULL,
    params          jsonb       NOT NULL DEFAULT '{}',
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    sha256          text        NOT NULL,
    payload         jsonb       NOT NULL
);
-- Same content fetched twice is stored once.
CREATE UNIQUE INDEX responses_dedupe
    ON raw.responses (platform, league_ext_id, season, resource, coalesce(scoring_period, -1), sha256);
CREATE INDEX responses_lookup
    ON raw.responses (platform, league_ext_id, season, resource, scoring_period);

-- ---------------------------------------------------------------------------
-- CORE: identity
-- ---------------------------------------------------------------------------

CREATE TABLE core.leagues (
    league_id   serial PRIMARY KEY,
    name        text NOT NULL
);

-- One league can live on several platforms over its lifetime.
CREATE TABLE core.league_platforms (
    league_id     int  NOT NULL REFERENCES core.leagues,
    platform      text NOT NULL,
    external_id   text NOT NULL,
    first_season  int,
    last_season   int,
    PRIMARY KEY (platform, external_id)
);

-- A real person. Survives team renames, platform switches, co-owner changes.
CREATE TABLE core.owners (
    owner_id      serial PRIMARY KEY,
    display_name  text NOT NULL UNIQUE,
    joined_season int,
    left_season   int
);

CREATE TABLE core.owner_external_ids (
    owner_id     int  NOT NULL REFERENCES core.owners,
    platform     text NOT NULL,
    external_id  text NOT NULL,          -- ESPN SWID, Sleeper user_id, ...
    PRIMARY KEY (platform, external_id)
);

CREATE TABLE core.players (
    player_id   serial PRIMARY KEY,
    full_name   text NOT NULL,
    position    text NOT NULL            -- QB RB WR TE K DST ...
);

CREATE TABLE core.player_external_ids (
    player_id    int  NOT NULL REFERENCES core.players,
    platform     text NOT NULL,          -- 'espn', 'sleeper', 'gsis', 'pfr', ...
    external_id  text NOT NULL,
    PRIMARY KEY (platform, external_id)
);
CREATE INDEX player_external_ids_player ON core.player_external_ids (player_id);

-- ---------------------------------------------------------------------------
-- CORE: seasons and rules (League Rules page)
-- ---------------------------------------------------------------------------

CREATE TABLE core.seasons (
    season_id             serial PRIMARY KEY,
    league_id             int  NOT NULL REFERENCES core.leagues,
    year                  int  NOT NULL,
    platform              text NOT NULL,
    data_tier             text NOT NULL CHECK (data_tier IN ('full', 'partial', 'archival')),
    team_count            int,
    regular_season_weeks  int,
    playoff_team_count    int,
    playoff_start_week    int,
    -- Headline scoring knobs, for filters and badges on records
    reception_points      numeric(4,2),     -- 1.0 PPR, 0.5 half, 0 standard
    te_premium            numeric(4,2) DEFAULT 0,  -- extra points per TE reception
    pass_td_points        numeric(4,2),
    scoring_label         text GENERATED ALWAYS AS (
        CASE
            WHEN reception_points IS NULL THEN NULL
            WHEN reception_points >= 1   THEN 'PPR'
            WHEN reception_points >= 0.5 THEN 'Half PPR'
            ELSE 'Standard'
        END ||
        CASE WHEN coalesce(te_premium, 0) > 0 THEN ' + TE premium' ELSE '' END
    ) STORED,
    -- Full rules, canonical stat key -> points, e.g. {"rec": 1, "rush_yds": 0.1}
    scoring_rules         jsonb,
    -- Roster template, e.g. {"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1,"DST":1,"K":1,"BE":6,"IR":1}
    roster_slots          jsonb,
    -- How the Draft was run: snake, or offline (picks entered by hand afterwards)
    draft_type            text CHECK (draft_type IN ('snake', 'offline')),
    notes                 text,
    UNIQUE (league_id, year)
);

-- Human-written changelog: "Added FLEX", "Switched to half PPR"
CREATE TABLE core.rule_changes (
    rule_change_id  serial PRIMARY KEY,
    league_id       int  NOT NULL REFERENCES core.leagues,
    effective_year  int  NOT NULL,
    summary         text NOT NULL,
    details         text
);

-- A team in one season. Linked to people through franchise_owners.
CREATE TABLE core.franchises (
    franchise_id      serial PRIMARY KEY,
    season_id         int  NOT NULL REFERENCES core.seasons,
    platform_team_id  text NOT NULL,
    team_name         text NOT NULL,
    abbrev            text,
    logo_url          text,
    -- Final results
    wins              int,
    losses            int,
    ties              int,
    points_for        numeric(8,2),
    points_against    numeric(8,2),
    regular_season_rank int,
    playoff_seed      int,
    final_rank        int,           -- 1 = champion
    UNIQUE (season_id, platform_team_id)
);

CREATE TABLE core.franchise_owners (
    franchise_id  int NOT NULL REFERENCES core.franchises,
    owner_id      int NOT NULL REFERENCES core.owners,
    is_primary    boolean NOT NULL DEFAULT true,
    PRIMARY KEY (franchise_id, owner_id)
);

-- ---------------------------------------------------------------------------
-- CORE: games
-- ---------------------------------------------------------------------------

-- Platform stat IDs -> canonical keys, so stats JSON is platform-neutral.
CREATE TABLE core.stat_definitions (
    platform          text NOT NULL,
    external_stat_id  text NOT NULL,
    canonical_key     text NOT NULL,     -- 'pass_yds', 'rush_yds', 'rec', 'rec_yds', 'rush_td', ...
    PRIMARY KEY (platform, external_stat_id)
);

CREATE TABLE core.matchups (
    matchup_id          serial PRIMARY KEY,
    season_id           int  NOT NULL REFERENCES core.seasons,
    matchup_period      int  NOT NULL,          -- can span several NFL weeks in playoffs
    first_week          int  NOT NULL,
    last_week           int  NOT NULL,
    home_franchise_id   int  NOT NULL REFERENCES core.franchises,
    away_franchise_id   int  REFERENCES core.franchises,   -- NULL = bye
    home_points         numeric(7,2),
    away_points         numeric(7,2),
    home_projected      numeric(7,2),
    away_projected      numeric(7,2),
    winner_franchise_id int  REFERENCES core.franchises,   -- NULL = tie or unplayed
    is_playoff          boolean NOT NULL DEFAULT false,
    bracket             text CHECK (bracket IN ('winners', 'consolation', 'toilet')),
    playoff_round       text,                   -- 'quarterfinal', 'semifinal', 'final', '3rd place'
    is_championship     boolean NOT NULL DEFAULT false
);
CREATE INDEX matchups_season_period ON core.matchups (season_id, matchup_period);

-- Every player on every roster every week, bench included.
CREATE TABLE core.lineup_entries (
    season_id         int  NOT NULL REFERENCES core.seasons,
    week              int  NOT NULL,
    franchise_id      int  NOT NULL REFERENCES core.franchises,
    player_id         int  NOT NULL REFERENCES core.players,
    slot              text NOT NULL,       -- QB RB WR TE FLEX DST K BE IR
    is_starter        boolean GENERATED ALWAYS AS (slot NOT IN ('BE', 'IR')) STORED,
    points            numeric(6,2),
    projected_points  numeric(6,2),
    PRIMARY KEY (season_id, week, franchise_id, player_id)
);
CREATE INDEX lineup_entries_player ON core.lineup_entries (player_id, season_id, week);

-- Raw per-week stats, so any season can be re-scored under any format.
CREATE TABLE core.player_week_stats (
    season_id        int  NOT NULL REFERENCES core.seasons,
    week             int  NOT NULL,
    player_id        int  NOT NULL REFERENCES core.players,
    source           text NOT NULL CHECK (source IN ('actual', 'projected')),
    nfl_team         text,
    stats            jsonb NOT NULL,         -- canonical_key -> value
    platform_points  numeric(6,2),           -- what the platform scored it at the time
    PRIMARY KEY (season_id, week, player_id, source)
);

-- ---------------------------------------------------------------------------
-- CORE: draft and transactions
-- ---------------------------------------------------------------------------

-- A Player in one Season, as the platform reports it for that Season: NFL team (one value per
-- Season; not provably the team on draft day; NULL = free agent), position, and Season points
-- (GLOSSARY: the platform's season total under that Season's scoring; NULL = none reported).
CREATE TABLE core.player_seasons (
    season_id      int  NOT NULL REFERENCES core.seasons,
    player_id      int  NOT NULL REFERENCES core.players,
    nfl_team       text,                    -- 'KC', 'BUF', ... (espn-api.md §5 proTeamId)
    position       text NOT NULL,           -- that Season's position: QB RB WR TE K D/ST ...
    season_points  numeric(8,2),
    PRIMARY KEY (season_id, player_id)
);

CREATE TABLE core.draft_picks (
    season_id       int  NOT NULL REFERENCES core.seasons,
    overall_pick    int  NOT NULL,
    round           int  NOT NULL,
    round_pick      int  NOT NULL,
    franchise_id    int  NOT NULL REFERENCES core.franchises,
    player_id       int  REFERENCES core.players,     -- NULL if archival player unknown
    is_keeper       boolean NOT NULL DEFAULT false,
    auction_price   int,
    PRIMARY KEY (season_id, overall_pick)
);

CREATE TABLE core.transactions (
    transaction_id    serial PRIMARY KEY,
    season_id         int  NOT NULL REFERENCES core.seasons,
    platform_txn_id   text,
    week              int,
    kind              text NOT NULL CHECK (kind IN ('trade', 'waiver', 'free_agent', 'drop', 'commissioner')),
    status            text,                 -- 'executed', 'vetoed', ...
    processed_at      timestamptz,
    faab_bid          int,
    UNIQUE (season_id, platform_txn_id)
);

CREATE TABLE core.transaction_items (
    transaction_id      int  NOT NULL REFERENCES core.transactions ON DELETE CASCADE,
    player_id           int  NOT NULL REFERENCES core.players,
    from_franchise_id   int  REFERENCES core.franchises,   -- NULL = from free agency
    to_franchise_id     int  REFERENCES core.franchises,   -- NULL = dropped
    PRIMARY KEY (transaction_id, player_id)
);

-- ---------------------------------------------------------------------------
-- CORE: curated content
-- ---------------------------------------------------------------------------

CREATE TABLE core.achievements (
    achievement_id  serial PRIMARY KEY,
    code            text NOT NULL UNIQUE,   -- 'week_200', 'won_with_low_score', ...
    name            text NOT NULL,
    description     text NOT NULL
);

CREATE TABLE core.owner_achievements (
    owner_id        int NOT NULL REFERENCES core.owners,
    achievement_id  int NOT NULL REFERENCES core.achievements,
    season_id       int NOT NULL REFERENCES core.seasons,
    week            int,
    context         jsonb,
    PRIMARY KEY (owner_id, achievement_id, season_id, week)
);

CREATE TABLE core.hall_of_fame (
    player_id     int  NOT NULL REFERENCES core.players,
    season_id     int  NOT NULL REFERENCES core.seasons,
    franchise_id  int  NOT NULL REFERENCES core.franchises,
    blurb         text,
    inducted_year int,
    PRIMARY KEY (player_id, season_id)
);

-- ---------------------------------------------------------------------------
-- STATS: derived views
-- ---------------------------------------------------------------------------

-- Franchise -> its primary owner
CREATE VIEW stats.franchise_owner AS
SELECT f.franchise_id, f.season_id, s.year, fo.owner_id, o.display_name
FROM core.franchises f
JOIN core.seasons s           ON s.season_id = f.season_id
JOIN core.franchise_owners fo ON fo.franchise_id = f.franchise_id AND fo.is_primary
JOIN core.owners o            ON o.owner_id = fo.owner_id;

-- One row per team per matchup, for records and head-to-head
CREATE VIEW stats.team_games AS
SELECT m.matchup_id, m.season_id, m.matchup_period, m.is_playoff, m.is_championship, m.bracket,
       side.franchise_id, side.opponent_id, side.points, side.opp_points,
       side.points - side.opp_points AS margin,
       CASE WHEN m.winner_franchise_id = side.franchise_id THEN 'W'
            WHEN m.winner_franchise_id IS NULL             THEN 'T'
            ELSE 'L' END AS result
FROM core.matchups m
CROSS JOIN LATERAL (VALUES
    (m.home_franchise_id, m.away_franchise_id, m.home_points, m.away_points),
    (m.away_franchise_id, m.home_franchise_id, m.away_points, m.home_points)
) AS side(franchise_id, opponent_id, points, opp_points)
WHERE side.franchise_id IS NOT NULL AND m.away_franchise_id IS NOT NULL;

-- Champion per season: winner of the championship Matchup, with its primary owner
CREATE VIEW stats.champions AS
SELECT s.year, f.franchise_id, f.team_name, fo.owner_id, fo.display_name
FROM core.matchups m
JOIN core.seasons s           ON s.season_id = m.season_id
JOIN core.franchises f        ON f.franchise_id = m.winner_franchise_id
JOIN stats.franchise_owner fo ON fo.franchise_id = f.franchise_id
WHERE m.is_championship;

-- Podium per season: final places 1-3 (rankCalculatedFinal), with regular-season record
CREATE VIEW stats.podium AS
SELECT s.year, f.final_rank, f.franchise_id, f.team_name, fo.owner_id, fo.display_name AS owner,
       f.wins, f.losses, f.ties
FROM core.franchises f
JOIN core.seasons s ON s.season_id = f.season_id
JOIN stats.franchise_owner fo ON fo.franchise_id = f.franchise_id
WHERE f.final_rank <= 3;

-- Last place per season: the highest playoff seed (worst regular season). Never final rank:
-- consolation games can move the regular-season loser up.
CREATE VIEW stats.last_place AS
SELECT DISTINCT ON (s.year)
       s.year, f.franchise_id, f.team_name, fo.owner_id, fo.display_name AS owner,
       f.wins, f.losses, f.ties, f.playoff_seed
FROM core.franchises f
JOIN core.seasons s ON s.season_id = f.season_id
JOIN stats.franchise_owner fo ON fo.franchise_id = f.franchise_id
ORDER BY s.year, f.playoff_seed DESC NULLS LAST;

-- Final standings per season, one row per Franchise. Points for is ESPN's regular-season figure,
-- which includes manual score adjustments (so it matches ESPN).
CREATE VIEW stats.standings AS
SELECT s.year, f.final_rank, f.franchise_id, f.team_name, fo.owner_id, fo.display_name AS owner,
       f.wins, f.losses, f.ties, f.points_for, f.points_against, f.playoff_seed
FROM core.franchises f
JOIN core.seasons s ON s.season_id = f.season_id
JOIN stats.franchise_owner fo ON fo.franchise_id = f.franchise_id;

-- Owner career totals
CREATE VIEW stats.owner_career AS
SELECT fo.owner_id, fo.display_name,
       count(DISTINCT f.season_id)                         AS seasons,
       sum(f.wins) AS wins, sum(f.losses) AS losses, sum(f.ties) AS ties,
       sum(f.points_for)                                   AS points_for,
       count(*) FILTER (WHERE f.final_rank = 1)            AS titles,
       count(*) FILTER (WHERE f.final_rank = 2)            AS runner_ups,
       -- Every Franchise has a seed (1..n); only seeds within the playoff field made the playoffs
       count(*) FILTER (WHERE f.playoff_seed <= s.playoff_team_count) AS playoff_apps
FROM core.franchises f
JOIN core.seasons s ON s.season_id = f.season_id
JOIN stats.franchise_owner fo ON fo.franchise_id = f.franchise_id
GROUP BY fo.owner_id, fo.display_name;

-- Trophy shelf: every Owner's titles and runner-up finishes (Season years), first and last Season,
-- Current team name (their most recent Franchise's name) and whether they've left (no Franchise in
-- the latest Season). Every Owner of a Franchise shares its honours, co-owners included, so this
-- reads core.franchise_owners rather than the primary-owner view. Final places come from
-- rankCalculatedFinal; the loader stops the build if they disagree with the championship Matchups.
CREATE VIEW stats.trophy_shelf AS
WITH owner_franchises AS (
    SELECT o.owner_id, o.display_name, s.year, f.franchise_id, f.team_name, f.final_rank
    FROM core.franchises f
    JOIN core.seasons s           ON s.season_id = f.season_id
    JOIN core.franchise_owners fo ON fo.franchise_id = f.franchise_id
    JOIN core.owners o            ON o.owner_id = fo.owner_id
)
SELECT ofr.owner_id, ofr.display_name,
       coalesce(array_agg(ofr.year ORDER BY ofr.year) FILTER (WHERE ofr.final_rank = 1), '{}') AS title_seasons,
       coalesce(array_agg(ofr.year ORDER BY ofr.year) FILTER (WHERE ofr.final_rank = 2), '{}') AS runner_up_seasons,
       min(ofr.year) AS first_season,
       max(ofr.year) AS last_season,
       -- Most recent Franchise; the best final rank breaks a tie if an Owner had two that Season
       (array_agg(ofr.team_name ORDER BY ofr.year DESC, ofr.final_rank, ofr.franchise_id))[1] AS current_team_name,
       max(ofr.year) < (SELECT max(year) FROM core.seasons) AS is_former
FROM owner_franchises ofr
GROUP BY ofr.owner_id, ofr.display_name;

-- One row per Owner per Matchup they played that counts toward a record (GLOSSARY: Playoff record):
-- kind 'regular' = regular-season Matchups; kind 'playoff' = winners'-bracket Matchups. Byes are
-- not games (team_games drops them). The Third-place game and other consolation Matchups count
-- toward neither, so they are left out. A two-week round is one Matchup, so it counts once.
CREATE VIEW stats.owner_games AS
SELECT s.year, g.matchup_id, a.owner_id, b.owner_id AS opponent_owner_id, g.result,
       CASE WHEN NOT g.is_playoff THEN 'regular' ELSE 'playoff' END AS kind
FROM stats.team_games g
JOIN core.seasons s           ON s.season_id = g.season_id
JOIN stats.franchise_owner a  ON a.franchise_id = g.franchise_id
JOIN stats.franchise_owner b  ON b.franchise_id = g.opponent_id
WHERE NOT g.is_playoff OR g.bracket = 'winners';

-- Head-to-head between Owners, regular season and playoffs apart (same rules as owner_games).
-- Only pairs who have met at least once have a row.
CREATE VIEW stats.head_to_head AS
SELECT owner_id, opponent_owner_id,
       count(*) FILTER (WHERE kind = 'regular' AND result = 'W') AS regular_wins,
       count(*) FILTER (WHERE kind = 'regular' AND result = 'L') AS regular_losses,
       count(*) FILTER (WHERE kind = 'regular' AND result = 'T') AS regular_ties,
       count(*) FILTER (WHERE kind = 'playoff' AND result = 'W') AS playoff_wins,
       count(*) FILTER (WHERE kind = 'playoff' AND result = 'L') AS playoff_losses,
       count(*) FILTER (WHERE kind = 'playoff' AND result = 'T') AS playoff_ties,
       count(*)                                                 AS meetings
FROM stats.owner_games
GROUP BY owner_id, opponent_owner_id;

-- Player season totals for the franchise that started them
CREATE VIEW stats.player_franchise_season AS
SELECT le.season_id, le.franchise_id, le.player_id,
       sum(le.points) FILTER (WHERE le.is_starter) AS started_points,
       sum(le.points)                             AS rostered_points,
       count(*) FILTER (WHERE le.is_starter)      AS weeks_started
FROM core.lineup_entries le
GROUP BY le.season_id, le.franchise_id, le.player_id;

-- Player season totals regardless of who rostered them (needs player_week_stats)
CREATE VIEW stats.player_season AS
SELECT pws.season_id, pws.player_id, p.full_name, p.position,
       sum(pws.platform_points) AS points,
       rank() OVER (PARTITION BY pws.season_id, p.position
                    ORDER BY sum(pws.platform_points) DESC NULLS LAST) AS position_rank
FROM core.player_week_stats pws
JOIN core.players p ON p.player_id = pws.player_id
WHERE pws.source = 'actual'
GROUP BY pws.season_id, pws.player_id, p.full_name, p.position;

-- Positional finish (GLOSSARY): rank by Season points among every Player at that position that
-- Season, drafted or not. Ties share the better rank.
CREATE VIEW stats.player_season_finish AS
SELECT ps.season_id, ps.player_id, ps.position, ps.season_points,
       rank() OVER (PARTITION BY ps.season_id, ps.position ORDER BY ps.season_points DESC) AS positional_finish
FROM core.player_seasons ps
WHERE ps.season_points IS NOT NULL;

-- Value over slot (GLOSSARY): overall pick minus the Pick's rank by Season points among that
-- Season's drafted Picks (ties share the better rank). Picks with no Player recorded get NULL and
-- are left out of the ranking.
CREATE VIEW stats.draft_value AS
SELECT dp.season_id, dp.overall_pick, dp.round, dp.round_pick, dp.franchise_id, dp.player_id,
       ps.season_points AS points, psf.positional_finish,
       CASE WHEN dp.player_id IS NOT NULL THEN
           dp.overall_pick - rank() OVER (PARTITION BY dp.season_id, dp.player_id IS NULL
                                          ORDER BY ps.season_points DESC)
       END AS value_over_slot
FROM core.draft_picks dp
LEFT JOIN core.player_seasons ps        ON ps.season_id = dp.season_id AND ps.player_id = dp.player_id
LEFT JOIN stats.player_season_finish psf ON psf.season_id = dp.season_id AND psf.player_id = dp.player_id;

-- Draft grade (GLOSSARY): the sum of a Franchise's Value over slot, ranked within the Season
CREATE VIEW stats.draft_grades AS
SELECT dv.season_id, dv.franchise_id,
       sum(dv.value_over_slot)::int AS total_value_over_slot,
       rank() OVER (PARTITION BY dv.season_id ORDER BY sum(dv.value_over_slot) DESC) AS grade_rank
FROM stats.draft_value dv
GROUP BY dv.season_id, dv.franchise_id;

-- Every Pick with its Owner (through franchise_owners), Player and value; Player columns are NULL for
-- a Pick with no Player recorded. The Draft slot is the Franchise's round-1 pick number. Position is
-- the Player's position that Season.
CREATE VIEW stats.draft_board AS
SELECT s.year, dp.overall_pick, dp.round, dp.round_pick, dp.franchise_id, f.team_name,
       fo.owner_id, fo.display_name AS owner,
       slot.round_pick AS draft_slot,
       p.full_name AS player_name, ps.position, ps.nfl_team,
       dv.points, dv.positional_finish, dv.value_over_slot
FROM core.draft_picks dp
JOIN core.seasons s             ON s.season_id = dp.season_id
JOIN core.franchises f          ON f.franchise_id = dp.franchise_id
JOIN stats.franchise_owner fo   ON fo.franchise_id = dp.franchise_id
JOIN core.draft_picks slot      ON slot.season_id = dp.season_id AND slot.franchise_id = dp.franchise_id
                               AND slot.round = 1
JOIN stats.draft_value dv       ON dv.season_id = dp.season_id AND dv.overall_pick = dp.overall_pick
LEFT JOIN core.players p        ON p.player_id = dp.player_id
LEFT JOIN core.player_seasons ps ON ps.season_id = dp.season_id AND ps.player_id = dp.player_id;

-- Points each acquired player scored as a starter for the new team, rest of that season
CREATE VIEW stats.acquisition_impact AS
SELECT t.transaction_id, t.season_id, t.week AS acquired_week, t.kind,
       ti.player_id, ti.from_franchise_id, ti.to_franchise_id,
       coalesce(sum(le.points) FILTER (WHERE le.is_starter), 0) AS started_points_after,
       count(le.*) FILTER (WHERE le.is_starter)                 AS weeks_started_after
FROM core.transactions t
JOIN core.transaction_items ti ON ti.transaction_id = t.transaction_id
LEFT JOIN core.lineup_entries le
       ON le.season_id = t.season_id
      AND le.franchise_id = ti.to_franchise_id
      AND le.player_id = ti.player_id
      AND le.week >= coalesce(t.week, 1)
WHERE ti.to_franchise_id IS NOT NULL
GROUP BY t.transaction_id, t.season_id, t.week, t.kind,
         ti.player_id, ti.from_franchise_id, ti.to_franchise_id;

-- Trade scorecard: each side's started points from what it received
CREATE VIEW stats.trade_scorecard AS
SELECT ai.transaction_id, ai.season_id, ai.to_franchise_id AS franchise_id,
       sum(ai.started_points_after) AS points_received
FROM stats.acquisition_impact ai
WHERE ai.kind = 'trade'
GROUP BY ai.transaction_id, ai.season_id, ai.to_franchise_id;

-- Weekly team scores with league-wide rank: highs, lows, all-play / luck index
CREATE VIEW stats.team_week_scores AS
SELECT le.season_id, le.week, le.franchise_id,
       sum(le.points) FILTER (WHERE le.is_starter) AS points,
       sum(le.points) FILTER (WHERE NOT le.is_starter AND le.slot = 'BE') AS bench_points,
       rank() OVER (PARTITION BY le.season_id, le.week
                    ORDER BY sum(le.points) FILTER (WHERE le.is_starter) DESC) AS week_rank,
       count(*) OVER (PARTITION BY le.season_id, le.week) AS teams_that_week
FROM core.lineup_entries le
GROUP BY le.season_id, le.week, le.franchise_id;

-- All-play record: how many teams you'd have beaten each week
CREATE VIEW stats.all_play AS
SELECT season_id, franchise_id,
       sum(teams_that_week - week_rank) AS all_play_wins,
       sum(week_rank - 1)               AS all_play_losses
FROM stats.team_week_scores
GROUP BY season_id, franchise_id;
