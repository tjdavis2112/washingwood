"""Load one Season of the ESPN archive into core.* (field paths: docs/research/espn-api.md).

Idempotent per Season: re-loading a Season replaces its Franchises, Matchups and Picks (ADR-0001).
ESPN IDs never become core keys: member IDs go to core.owner_external_ids, the league ID to
core.league_platforms, player IDs to core.player_external_ids (ADR-0002).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from psycopg import Connection
from psycopg.types.json import Jsonb

from washingwood.owners import OwnerMap, OwnerMappingError

PLATFORM = "espn"

# playoffTierType -> core.matchups.bracket (espn-api.md §3)
BRACKETS = {
    "NONE": None,
    "WINNERS_BRACKET": "winners",
    "WINNERS_CONSOLATION_LADDER": "consolation",
    "LOSERS_CONSOLATION_LADDER": "toilet",
}

# lineupSlotId -> slot label (espn-api.md §5)
SLOTS = {"0": "QB", "1": "TQB", "2": "RB", "3": "RB/WR", "4": "WR", "5": "WR/TE", "6": "TE", "7": "OP",
         "16": "D/ST", "17": "K", "20": "BE", "21": "IR", "23": "FLEX"}  # fmt: skip

STAT_PASS_TD, STAT_RECEPTION = 4, 53
POSITION_WR, POSITION_TE = "3", "4"  # defaultPositionId keys of pointsOverrides

# defaultPositionId -> position (espn-api.md §5 ROSTER_POSITION_MAP; not the lineupSlotId map)
POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 7: "P", 9: "DT", 10: "DE", 11: "LB", 12: "CB",
             13: "S", 14: "HC", 15: "TQB", 16: "D/ST"}  # fmt: skip

# proTeamId -> NFL team abbreviation (espn-api.md §5). 0 = free agent: no team.
NFL_TEAMS = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB",
             10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO",
             19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB",
             28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"}  # fmt: skip

# settings.draftSettings.type -> core.seasons.draft_type (espn-api.md §6, §9)
DRAFT_TYPES = {"SNAKE": "snake", "OFFLINE": "offline"}
NO_PLAYER = -1  # playerId of a Pick with no Player recorded (2018 offline draft)

# ESPN statId -> platform-neutral key for core.seasons.scoring_rules (espn-api.md §5; ADR-0002)
CANONICAL_STATS = {3: "pass_yds", 4: "pass_td", 20: "pass_int", 24: "rush_yds", 25: "rush_td",
                   42: "rec_yds", 43: "rec_td", 53: "rec", 72: "fum_lost"}  # fmt: skip


class LoadError(ValueError):
    """The archive doesn't have the shape the loader relies on."""


@dataclass(frozen=True)
class SeasonFiles:
    year: int
    settings: dict
    teams: dict
    matchups: dict
    draft: dict
    players: dict[int, dict]  # players.json by ESPN player id
    pool: dict[int, dict]  # player_pool.json `player` objects by ESPN player id
    has_lineups: bool
    season_dir: Path  # box scores are read Week by Week from here, not held in memory

    @classmethod
    def read(cls, season_dir: Path) -> SeasonFiles:
        def load(name):
            path = season_dir / f"{name}.json"
            if not path.exists():
                raise LoadError(f"Season {season_dir.name}: missing {path.name}")
            return json.loads(path.read_text(encoding="utf-8"))

        return cls(
            year=int(season_dir.name),
            settings=load("league_mSettings"),
            teams=load("league_mTeam"),
            matchups=load("league_mMatchupScore"),
            draft=load("league_mDraftDetail"),
            players={p["id"]: p for p in load("players")},
            pool={e["player"]["id"]: e["player"] for e in load("player_pool")["players"]},
            has_lineups=_has_lineups(season_dir / "boxscore_w01.json"),
            season_dir=season_dir,
        )


def _has_lineups(boxscore: Path) -> bool:
    """Data tier: full when week-1 box scores carry lineups (espn-api.md §4, §9)."""
    if not boxscore.exists():
        return False
    doc = json.loads(boxscore.read_text(encoding="utf-8"))
    return any(
        side.get("rosterForCurrentScoringPeriod", {}).get("entries")
        for m in doc.get("schedule", [])
        for side in (m.get("home") or {}, m.get("away") or {})
    )


def load_season(conn: Connection, files: SeasonFiles, owner_map: OwnerMap) -> None:
    """Replace one Season's rows in core.* inside the caller's transaction."""
    franchise_owners = _map_owners(files, owner_map)  # fail before touching the database
    _check_seeds(files)
    picks = _check_picks(files)
    league_id = _upsert_league(conn, files)
    season_id = _upsert_season(conn, league_id, files)

    conn.execute(
        "DELETE FROM core.franchise_owners WHERE franchise_id IN "
        "(SELECT franchise_id FROM core.franchises WHERE season_id = %s)",
        (season_id,),
    )
    conn.execute("DELETE FROM core.transactions WHERE season_id = %s", (season_id,))  # items cascade
    conn.execute("DELETE FROM core.lineup_entries WHERE season_id = %s", (season_id,))
    conn.execute("DELETE FROM core.draft_picks WHERE season_id = %s", (season_id,))
    conn.execute("DELETE FROM core.player_seasons WHERE season_id = %s", (season_id,))
    conn.execute("DELETE FROM core.matchups WHERE season_id = %s", (season_id,))
    conn.execute("DELETE FROM core.franchises WHERE season_id = %s", (season_id,))

    franchise_ids = {}
    for t in sorted(files.teams["teams"], key=lambda t: t["id"]):
        rec = t["record"]["overall"]
        franchise_ids[t["id"]] = conn.execute(
            """INSERT INTO core.franchises (season_id, platform_team_id, team_name, abbrev, wins, losses, ties,
                   points_for, points_against, playoff_seed, final_rank)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING franchise_id""",
            (season_id, str(t["id"]), t["name"], t.get("abbrev"), rec["wins"], rec["losses"], rec["ties"],
             rec["pointsFor"], rec["pointsAgainst"], t["playoffSeed"], t["rankCalculatedFinal"]),
        ).fetchone()[0]  # fmt: skip
        for owner, is_primary in franchise_owners[t["id"]]:
            conn.execute(
                "INSERT INTO core.franchise_owners (franchise_id, owner_id, is_primary) VALUES (%s, %s, %s)",
                (franchise_ids[t["id"]], _upsert_owner(conn, owner), is_primary),
            )

    _matchups(conn, season_id, files, franchise_ids)
    _draft(conn, season_id, files, picks, franchise_ids)
    if files.has_lineups:  # trades are scored from lineups, and need the weekly rosters that come with them
        _lineups(conn, season_id, files, franchise_ids)
        _trades(conn, season_id, files, franchise_ids)


def _check_picks(files: SeasonFiles) -> list[dict]:
    """draftDetail.picks, checked: teams x rounds Picks numbered 1..N, each Franchise once per round,
    and every recorded Player listed in players.json (espn-api.md §6). Returns them in pick order."""
    draft_type = files.settings["settings"].get("draftSettings", {}).get("type")
    if draft_type not in DRAFT_TYPES:
        raise LoadError(f"Season {files.year}: unsupported draft type {draft_type!r} (expected SNAKE or OFFLINE)")
    picks = sorted(files.draft["draftDetail"]["picks"], key=lambda p: p["overallPickNumber"])
    teams = {t["id"] for t in files.teams["teams"]}
    rounds = max((p["roundId"] for p in picks), default=0)
    if len(picks) != len(teams) * rounds:
        raise LoadError(
            f"Season {files.year}: the Draft has {len(picks)} picks, expected {len(teams) * rounds} "
            f"({len(teams)} teams x {rounds} rounds)"
        )
    if [p["overallPickNumber"] for p in picks] != list(range(1, len(picks) + 1)):
        raise LoadError(f"Season {files.year}: Draft pick numbers aren't 1..{len(picks)}")
    for rnd in range(1, rounds + 1):
        in_round = [p for p in picks if p["roundId"] == rnd]
        if sorted(p["teamId"] for p in in_round) != sorted(teams):
            raise LoadError(f"Season {files.year}: Draft round {rnd} doesn't give every team exactly one pick")
        if sorted(p["roundPickNumber"] for p in in_round) != list(range(1, len(teams) + 1)):
            raise LoadError(f"Season {files.year}: Draft round {rnd} pick numbers aren't 1..{len(teams)}")
    for p in picks:
        if p["playerId"] != NO_PLAYER and p["playerId"] not in files.players:
            raise LoadError(
                f"Season {files.year}: pick {p['overallPickNumber']} drafted ESPN player {p['playerId']}, "
                "who is not in players.json"
            )
        if p["playerId"] != NO_PLAYER and season_points(files, p["playerId"]) is None:
            raise LoadError(
                f"Season {files.year}: pick {p['overallPickNumber']} drafted ESPN player {p['playerId']}, "
                "who has no Season points (season-total actual row) in player_pool.json"
            )
    return picks


def season_points(files: SeasonFiles, espn_player_id: int) -> float | None:
    """Season points (GLOSSARY): the pool's season-total actual row for this Season under league
    scoring (scoringPeriodId 0, statSourceId 0, statSplitTypeId 0, appliedTotal; espn-api.md §5)."""
    player = files.pool.get(espn_player_id)
    rows = [
        r
        for r in (player or {}).get("stats", [])
        if r.get("seasonId") == files.year
        and r.get("scoringPeriodId") == 0
        and r.get("statSourceId") == 0
        and r.get("statSplitTypeId") == 0
    ]
    if len(rows) > 1:
        raise LoadError(f"Season {files.year}: ESPN player {espn_player_id} has {len(rows)} season-total rows")
    return rows[0].get("appliedTotal", 0.0) if rows else None


def _draft(conn: Connection, season_id: int, files: SeasonFiles, picks: list[dict], franchise_ids) -> None:
    """Players this Season (every drafted Player plus every pool Player, so Positional finish ranks
    against undrafted Players too), then the Picks. memberId (personal) is never stored."""
    conn.execute(
        "UPDATE core.seasons SET draft_type = %s WHERE season_id = %s",
        (DRAFT_TYPES[files.settings["settings"]["draftSettings"]["type"]], season_id),
    )
    # players.json describes drafted Players; the pool describes the rest (same fields)
    drafted = {p["playerId"] for p in picks if p["playerId"] != NO_PLAYER}
    season_players = {pid: files.pool[pid] for pid in files.pool}
    season_players.update({pid: files.players[pid] for pid in drafted})
    player_ids = {}
    for espn_id in sorted(season_players):
        espn_player = season_players[espn_id]
        player_ids[espn_id] = player_id = _upsert_player(conn, files, espn_player)
        conn.execute(
            """INSERT INTO core.player_seasons (season_id, player_id, nfl_team, position, season_points)
               VALUES (%s, %s, %s, %s, %s)""",
            (season_id, player_id, NFL_TEAMS.get(espn_player["proTeamId"]),
             POSITIONS[espn_player["defaultPositionId"]], season_points(files, espn_id)),
        )  # fmt: skip
    for p in picks:
        player_id = player_ids.get(p["playerId"])
        conn.execute(
            """INSERT INTO core.draft_picks (season_id, overall_pick, round, round_pick, franchise_id, player_id,
                   is_keeper)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (season_id, p["overallPickNumber"], p["roundId"], p["roundPickNumber"], franchise_ids[p["teamId"]],
             player_id, bool(p.get("keeper"))),
        )  # fmt: skip


def _upsert_player(conn: Connection, files: SeasonFiles, player: dict) -> int:
    """One core.players row per ESPN player id. Name and position follow the latest Season that lists
    the Player, so the load order of Seasons doesn't change the result."""
    position = POSITIONS.get(player["defaultPositionId"])
    if position is None:
        raise LoadError(
            f"Season {files.year}: ESPN player {player['id']} has unknown position id {player['defaultPositionId']}"
        )
    ext_id = str(player["id"])
    row = conn.execute(
        "SELECT player_id FROM core.player_external_ids WHERE platform = %s AND external_id = %s", (PLATFORM, ext_id)
    ).fetchone()
    if row is None:
        player_id = conn.execute(
            "INSERT INTO core.players (full_name, position) VALUES (%s, %s) RETURNING player_id",
            (player["fullName"], position),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO core.player_external_ids (player_id, platform, external_id) VALUES (%s, %s, %s)",
            (player_id, PLATFORM, ext_id),
        )
        return player_id
    player_id = row[0]
    # Rename only from a Season at least as new as every other Season that lists the Player
    conn.execute(
        """UPDATE core.players SET full_name = %s, position = %s
           WHERE player_id = %s AND NOT EXISTS (
               SELECT 1 FROM core.player_seasons ps JOIN core.seasons s USING (season_id)
               WHERE ps.player_id = %s AND s.year > %s)""",
        (player["fullName"], position, player_id, player_id, files.year),
    )
    return player_id


def _check_seeds(files: SeasonFiles) -> None:
    """playoffSeed ranks every Franchise 1..n by regular season. Last place depends on it, so it must be whole."""
    seeds = sorted(t.get("playoffSeed") or 0 for t in files.teams["teams"])
    if seeds != list(range(1, len(seeds) + 1)):
        raise LoadError(f"Season {files.year}: playoff seeds should be 1..{len(seeds)}, found {seeds}")


def _map_owners(files: SeasonFiles, owner_map: OwnerMap):
    """team id -> [(Owner, is_primary)]. Any unmapped member fails the build (ADR-0005)."""
    result = {}
    for t in files.teams["teams"]:
        members = t.get("owners") or []
        if not members:
            raise OwnerMappingError(f"Season {files.year}: team {t['id']} ({t['name']}) has no ESPN members")
        primary: dict = {}  # Owner -> is primary; one entry per Owner even if several of their accounts are listed
        for member in members:
            owner = owner_map.for_member(member)
            if owner is None:
                raise OwnerMappingError(
                    f"Season {files.year}: team {t['id']} ({t['name']}) is not mapped. "
                    f"Add ESPN member {member} to an Owner in owners.yaml."
                )
            primary[owner] = primary.get(owner, False) or member == t.get("primaryOwner")
        mapped = list(primary.items())
        # A Franchise has exactly one Owner (GLOSSARY: Franchise); several accounts of that one Owner are fine
        if len(mapped) > 1:
            raise OwnerMappingError(
                f"Season {files.year}: team {t['id']} ({t['name']}) maps to {len(mapped)} Owners, "
                "but a Franchise has exactly one Owner. Fix its ESPN members in owners.yaml."
            )
        if not any(p for _, p in mapped):
            mapped[0] = (mapped[0][0], True)
        result[t["id"]] = mapped
    return result


def _upsert_league(conn: Connection, files: SeasonFiles) -> int:
    ext_id, name = str(files.settings["id"]), files.settings["settings"]["name"]
    row = conn.execute(
        "SELECT league_id FROM core.league_platforms WHERE platform = %s AND external_id = %s", (PLATFORM, ext_id)
    ).fetchone()
    if row:
        return row[0]
    league_id = conn.execute("INSERT INTO core.leagues (name) VALUES (%s) RETURNING league_id", (name,)).fetchone()[0]
    conn.execute(
        "INSERT INTO core.league_platforms (league_id, platform, external_id) VALUES (%s, %s, %s)",
        (league_id, PLATFORM, ext_id),
    )
    return league_id


def _upsert_season(conn: Connection, league_id: int, files: SeasonFiles) -> int:
    s = files.settings["settings"]
    sched = s["scheduleSettings"]
    regular = sched["matchupPeriodCount"]
    first_playoff = sched["matchupPeriods"].get(str(regular + 1))
    items = {i["statId"]: i for i in s["scoringSettings"]["scoringItems"]}
    # No reception item at all means receptions score nothing (Standard)
    reception = _points_for(items.get(STAT_RECEPTION), POSITION_WR) or 0.0
    te = _points_for(items.get(STAT_RECEPTION), POSITION_TE) or 0.0
    slots = {
        SLOTS.get(k, k): v
        for k, v in sorted(s["rosterSettings"]["lineupSlotCounts"].items(), key=lambda kv: int(kv[0]))
        if v
    }
    pass_td = items.get(STAT_PASS_TD, {}).get("points")
    # Offensive points per unit, as a WR would score them (TE premium is stored separately)
    rules = {key: _points_for(items[stat], POSITION_WR) for stat, key in CANONICAL_STATS.items() if stat in items}

    return conn.execute(
        """INSERT INTO core.seasons (league_id, year, platform, data_tier, team_count, regular_season_weeks,
               playoff_team_count, playoff_start_week, reception_points, te_premium, pass_td_points, roster_slots,
               scoring_rules)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (league_id, year) DO UPDATE SET
               platform = EXCLUDED.platform, data_tier = EXCLUDED.data_tier, team_count = EXCLUDED.team_count,
               regular_season_weeks = EXCLUDED.regular_season_weeks, playoff_team_count = EXCLUDED.playoff_team_count,
               playoff_start_week = EXCLUDED.playoff_start_week, reception_points = EXCLUDED.reception_points,
               te_premium = EXCLUDED.te_premium, pass_td_points = EXCLUDED.pass_td_points,
               roster_slots = EXCLUDED.roster_slots, scoring_rules = EXCLUDED.scoring_rules
           RETURNING season_id""",
        (league_id, files.year, PLATFORM, "full" if files.has_lineups else "partial", s["size"],
         max(sched["matchupPeriods"][str(regular)]), sched["playoffTeamCount"],
         min(first_playoff) if first_playoff else None, reception,
         (te - reception) if te is not None and reception is not None else 0, pass_td, Jsonb(slots),
         Jsonb(rules)),
    ).fetchone()[0]  # fmt: skip


def _points_for(item: dict | None, position: str) -> float | None:
    """Points for a stat at a position: the override if present, else the base (espn-api.md §1)."""
    if item is None:
        return None
    return item.get("pointsOverrides", {}).get(position, item["points"])


def _upsert_owner(conn: Connection, owner) -> int:
    owner_id = conn.execute(
        """INSERT INTO core.owners (display_name) VALUES (%s)
           ON CONFLICT (display_name) DO UPDATE SET display_name = EXCLUDED.display_name RETURNING owner_id""",
        (owner.name,),
    ).fetchone()[0]
    for member in owner.espn_members:
        conn.execute(
            """INSERT INTO core.owner_external_ids (owner_id, platform, external_id) VALUES (%s, %s, %s)
               ON CONFLICT (platform, external_id) DO UPDATE SET owner_id = EXCLUDED.owner_id""",
            (owner_id, PLATFORM, member),
        )
    return owner_id


def _matchups(conn: Connection, season_id: int, files: SeasonFiles, franchise_ids: dict[int, int]) -> None:
    periods = files.settings["settings"]["scheduleSettings"]["matchupPeriods"]
    schedule = sorted(files.matchups["schedule"], key=lambda m: (m["matchupPeriodId"], m["id"]))
    unplayed = [m for m in schedule if m.get("away") and m["winner"] not in ("HOME", "AWAY", "TIE")]
    if unplayed:
        m = unplayed[0]
        raise LoadError(
            f"Season {files.year}: {len(unplayed)} Matchup(s) have no result, e.g. period {m['matchupPeriodId']} "
            f"({m['winner']}). Only finished Seasons can be loaded."
        )
    final = _championship(files, schedule)
    third = _third_place_game(files, schedule)
    _check_against_espn_places(files, final, third)
    rounds = {**_winners_bracket_rounds(schedule), id(third): THIRD_PLACE}

    for m in schedule:
        weeks = periods[str(m["matchupPeriodId"])]
        home, away = m["home"], m.get("away")
        winner = _winner(m)
        conn.execute(
            """INSERT INTO core.matchups (season_id, matchup_period, first_week, last_week, home_franchise_id,
                   away_franchise_id, home_points, away_points, home_adjustment, away_adjustment,
                   winner_franchise_id, is_playoff, bracket, playoff_round, is_championship)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (season_id, m["matchupPeriodId"], min(weeks), max(weeks), franchise_ids[home["teamId"]],
             franchise_ids[away["teamId"]] if away else None,
             home["totalPoints"], away["totalPoints"] if away else None,
             home.get("adjustment") or 0, (away.get("adjustment") or 0) if away else None,
             franchise_ids[winner] if winner else None, m["playoffTierType"] != "NONE",
             BRACKETS[m["playoffTierType"]], rounds.get(id(m)), m is final),
        )  # fmt: skip


def _winner(m: dict) -> int | None:
    """Winning team id, or None for a tie, bye or unplayed Matchup."""
    side = {"HOME": m["home"], "AWAY": m.get("away")}.get(m["winner"])
    return side["teamId"] if side else None


def _loser(m: dict) -> int | None:
    side = {"HOME": m.get("away"), "AWAY": m["home"]}.get(m["winner"])
    return side["teamId"] if side else None


# core.matchups.playoff_round values. Winners' bracket rounds are counted back from the championship.
ROUND_LABELS = ["final", "semifinal", "quarterfinal"]
THIRD_PLACE = "3rd place"


def _winners_bracket_rounds(schedule: list[dict]) -> dict[int, str]:
    """id(matchup) -> playoff_round for every WINNERS_BRACKET Matchup, byes included."""
    wb = [m for m in schedule if m["playoffTierType"] == "WINNERS_BRACKET"]
    periods = sorted({m["matchupPeriodId"] for m in wb}, reverse=True)
    label = {
        p: ROUND_LABELS[i] if i < len(ROUND_LABELS) else f"round {len(periods) - i}" for i, p in enumerate(periods)
    }
    return {id(m): label[m["matchupPeriodId"]] for m in wb}


def _championship(files: SeasonFiles, schedule: list[dict]) -> dict:
    """The single WINNERS_BRACKET Matchup in the last Matchup period (espn-api.md §3)."""
    last = max(m["matchupPeriodId"] for m in schedule)
    finals = [m for m in schedule if m["matchupPeriodId"] == last and m["playoffTierType"] == "WINNERS_BRACKET"]
    if len(finals) != 1:
        raise LoadError(
            f"Season {files.year}: expected one WINNERS_BRACKET Matchup in period {last}, found {len(finals)}"
        )
    return finals[0]


def _third_place_game(files: SeasonFiles, schedule: list[dict]) -> dict:
    """The last-period WINNERS_CONSOLATION_LADDER Matchup between the two semifinal losers.

    Tier alone isn't enough: from 2020 the 5th-place game shares the tier and the period."""
    last = max(m["matchupPeriodId"] for m in schedule)
    semis = [m for m in schedule if m["matchupPeriodId"] == last - 1 and m["playoffTierType"] == "WINNERS_BRACKET"]
    semi_losers = {_loser(m) for m in semis}
    games = [
        m
        for m in schedule
        if m["matchupPeriodId"] == last
        and m["playoffTierType"] == "WINNERS_CONSOLATION_LADDER"
        and {m["home"]["teamId"], (m.get("away") or {}).get("teamId")} == semi_losers
    ]
    if len(semis) != 2 or len(games) != 1:
        raise LoadError(f"Season {files.year}: couldn't find the Third-place game between the semifinal losers")
    return games[0]


def _check_against_espn_places(files: SeasonFiles, final: dict, third: dict) -> None:
    """Final placement comes from rankCalculatedFinal. The bracket must agree with it, or the build stops."""
    rank = {t["id"]: t["rankCalculatedFinal"] for t in files.teams["teams"]}
    expected = [
        ("Champion", _winner(final), 1),
        ("runner-up", _loser(final), 2),
        ("Third-place game winner", _winner(third), 3),
    ]
    for label, team_id, place in expected:
        if rank.get(team_id) != place:
            raise LoadError(
                f"Season {files.year}: the {label} (team {team_id}) is ranked {rank.get(team_id)} by ESPN, not "
                f"{place}. The Third-place game or championship disagrees with ESPN's final places."
            )


STARTER_EXCLUDED = {"BE", "IR"}


def _lineups(conn: Connection, season_id: int, files: SeasonFiles, franchise_ids: dict[int, int]) -> None:
    """Every Week's lineups from boxscore_wNN.json into core.lineup_entries (espn-api.md §4): each side's
    rosterForCurrentScoringPeriod.entries (never rosterForMatchupPeriod). Points come from the actual
    stat row (none = didn't play), the projection from statSourceId 1, the NFL team from that game's
    actual row. A team-Week whose starters don't add up to its score stops the build."""
    periods = files.settings["settings"]["scheduleSettings"]["matchupPeriods"]
    last_week = max(w for weeks in periods.values() for w in weeks)
    team_names = {t["id"]: t["name"] for t in files.teams["teams"]}
    known = dict(
        conn.execute("SELECT external_id, player_id FROM core.player_external_ids WHERE platform = %s", (PLATFORM,))
    )
    in_season = {
        pid for (pid,) in conn.execute("SELECT player_id FROM core.player_seasons WHERE season_id = %s", (season_id,))
    }
    rows = []
    for week in range(1, last_week + 1):
        path = files.season_dir / f"boxscore_w{week:02d}.json"
        if not path.exists():
            raise LoadError(f"Season {files.year}: missing {path.name}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        for m in doc.get("schedule", []):
            for side in (m.get("home"), m.get("away")):
                if not side:
                    continue
                entries = (side.get("rosterForCurrentScoringPeriod") or {}).get("entries") or []
                starters_total = 0.0
                for e in entries:
                    slot = SLOTS.get(str(e["lineupSlotId"]))
                    if slot is None:
                        raise LoadError(f"Season {files.year}, Week {week}: unknown lineupSlotId {e['lineupSlotId']}")
                    entry = e["playerPoolEntry"]
                    player = entry["player"]
                    if slot not in STARTER_EXCLUDED:
                        starters_total += entry.get("appliedStatTotal") or 0
                    player_id = known.get(str(player["id"]))
                    if player_id is None:
                        player_id = known[str(player["id"])] = _upsert_player(conn, files, player)
                    if player_id not in in_season:
                        conn.execute(
                            """INSERT INTO core.player_seasons (season_id, player_id, nfl_team, position)
                               VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                            (season_id, player_id, NFL_TEAMS.get(player.get("proTeamId")),
                             POSITIONS[player["defaultPositionId"]]),
                        )  # fmt: skip
                        in_season.add(player_id)
                    actual = _week_row(player, files.year, week, source=0)
                    projected = _week_row(player, files.year, week, source=1)
                    rows.append(
                        (season_id, week, franchise_ids[side["teamId"]], player_id, slot,
                         actual.get("appliedTotal") if actual else None,
                         projected.get("appliedTotal") if projected else None,
                         NFL_TEAMS.get((actual or projected or {}).get("proTeamId")))
                    )  # fmt: skip
                expected = (side.get("pointsByScoringPeriod") or {}).get(str(week))
                if entries and expected is not None and abs(round(starters_total, 2) - expected) > 0.011:
                    raise LoadError(
                        f"Season {files.year}, Week {week}: {team_names[side['teamId']]}'s starters add up to "
                        f"{round(starters_total, 2)}, but the Matchup score for the Week is {expected}"
                    )
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO core.lineup_entries (season_id, week, franchise_id, player_id, slot, points,
                   projected_points, nfl_team)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            rows,
        )


def _week_row(player: dict, year: int, week: int, *, source: int) -> dict | None:
    """The player's single-Week stat row: statSourceId 0 = actual, 1 = projection (espn-api.md §4)."""
    return next(
        (
            r
            for r in player.get("stats", [])
            if r.get("statSourceId") == source
            and r.get("statSplitTypeId") == 1
            and r.get("scoringPeriodId") == week
            and r.get("seasonId", year) == year
        ),
        None,
    )


# -- trades (espn-api.md §7) ---------------------------------------------------

Move = tuple[int, int, int, int]  # (ESPN player id, from team id, to team id, first Week on the new roster)


@dataclass
class _Trade:
    """One executed trade: every mTransactions2 row that shares its relatedTransactionId (one row in 2018)."""

    rows: list[dict]
    legs: set[Move] | None = None  # resolved legs
    week: int | None = None  # effective Week: the first Week the received Players are on the new roster

    @property
    def accept(self) -> dict:
        return self.rows[0]

    @property
    def accepted_week(self) -> int:
        return self.accept["scoringPeriodId"]

    @property
    def acceptor(self) -> int:
        return self.accept["teamId"]

    @property
    def window(self) -> tuple[int, int]:
        """Players show on their new team in roster_w(N) or roster_w(N+1), N = the accepted Week."""
        return self.accepted_week, self.accepted_week + 1

    @property
    def platform_id(self) -> str:
        return self.accept.get("relatedTransactionId") or self.accept["id"]


def _trades(conn: Connection, season_id: int, files: SeasonFiles, franchise_ids: dict[int, int]) -> None:
    """Executed trades into core.transactions (kind 'trade') and their legs into core.transaction_items.

    Counting (espn-api.md §7): one trade per TRADE_ACCEPT without relatedTransactionId (2018), else one
    per distinct relatedTransactionId among TRADE_ACCEPT rows, minus those a commissioner vetoed. Legs
    come from TRADE items where any row has them; otherwise from the weekly roster diff. Every Player
    who changes teams without an executed add must belong to a trade, and the count must match ESPN's
    transactionCounter, or the build stops."""
    last_week = max(w for ws in files.settings["settings"]["scheduleSettings"]["matchupPeriods"].values() for w in ws)
    team_names = {t["id"]: t["name"] for t in files.teams["teams"]}
    rosters = {0: _draft_rosters(files)} | {w: _roster(files, w) for w in range(1, last_week + 1)}
    rows = [r for w in range(1, last_week + 1) for r in _transactions(files, w)]
    trades = _executed_trades(rows)

    expected = sum((t.get("transactionCounter") or {}).get("trades", 0) for t in files.teams["teams"]) / 2
    if len(trades) != expected:
        raise LoadError(
            f"Season {files.year}: {len(trades)} trade(s) found, but ESPN's transactionCounter says {expected:g}"
        )

    moves = _unexplained_moves(rosters, _executed_adds(rows))
    unclaimed = _resolve_trades(files, trades, moves, team_names)
    if unclaimed:
        pid, src, dst, week = min(unclaimed, key=lambda m: (m[3], m[0]))
        raise LoadError(
            f"Season {files.year}, Week {week}: ESPN player {pid} moved from {team_names.get(src, src)} to "
            f"{team_names.get(dst, dst)} with no trade or executed add to explain it"
        )

    known = dict(
        conn.execute("SELECT external_id, player_id FROM core.player_external_ids WHERE platform = %s", (PLATFORM,))
    )
    for trade in sorted(trades, key=lambda t: (t.week, t.platform_id)):
        process = next((r["processDate"] for r in trade.rows if r.get("processDate")), None)
        txn_id = conn.execute(
            """INSERT INTO core.transactions (season_id, platform_txn_id, week, kind, status, processed_at)
               VALUES (%s, %s, %s, 'trade', 'executed', to_timestamp(%s / 1000.0)) RETURNING transaction_id""",
            (season_id, trade.platform_id, trade.week, process),
        ).fetchone()[0]
        for pid, src, dst, _ in sorted(trade.legs):
            if str(pid) not in known:
                raise LoadError(f"Season {files.year}, Week {trade.week}: traded ESPN player {pid} is in no lineup")
            conn.execute(
                """INSERT INTO core.transaction_items (transaction_id, player_id, from_franchise_id, to_franchise_id)
                   VALUES (%s, %s, %s, %s)""",
                (txn_id, known[str(pid)], franchise_ids[src], franchise_ids[dst]),
            )


def _season_file(files: SeasonFiles, name: str) -> dict:
    path = files.season_dir / f"{name}.json"
    if not path.exists():
        raise LoadError(f"Season {files.year}: missing {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _roster(files: SeasonFiles, week: int) -> dict[int, set[int]]:
    """team id -> ESPN player ids on its roster_wNN.json (espn-api.md §4)."""
    doc = _season_file(files, f"roster_w{week:02d}")
    return {t["id"]: {e["playerId"] for e in (t.get("roster") or {}).get("entries", [])} for t in doc["teams"]}


def _draft_rosters(files: SeasonFiles) -> dict[int, set[int]]:
    """The roster before Week 1: each team's drafted Players (espn-api.md §6)."""
    rosters: dict[int, set[int]] = {t["id"]: set() for t in files.teams["teams"]}
    for p in files.draft["draftDetail"]["picks"]:
        if p["playerId"] != NO_PLAYER:
            rosters[p["teamId"]].add(p["playerId"])
    return rosters


def _transactions(files: SeasonFiles, week: int) -> list[dict]:
    return _season_file(files, f"transactions_w{week:02d}").get("transactions") or []


def _executed_adds(rows: list[dict]) -> set[tuple[int, int, int]]:
    """(ESPN player id, receiving team, Week) of every executed waiver or free-agent add. The receiving team
    is the item's toTeamId, never the row's teamId (espn-api.md §7)."""
    return {
        (item["playerId"], item["toTeamId"], r["scoringPeriodId"])
        for r in rows
        if r["type"] in ("WAIVER", "FREEAGENT") and r.get("status") == "EXECUTED"
        for item in r.get("items") or []
        if item["type"] == "ADD"
    }


def _executed_trades(rows: list[dict]) -> list[_Trade]:
    """Accepted trades minus commissioner vetoes, in the order they were accepted."""
    vetoed = {r.get("relatedTransactionId") for r in rows if r["type"] == "TRADE_VETO" and r.get("isLeagueManager")}
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        if r["type"] == "TRADE_ACCEPT":
            grouped.setdefault(r.get("relatedTransactionId") or r["id"], []).append(r)
    trades = [_Trade(sorted(rs, key=lambda r: (r["proposedDate"], r["id"]))) for rs in grouped.values()]
    trades = [t for t in trades if t.platform_id not in vetoed - {None}]
    return sorted(trades, key=lambda t: (t.accepted_week, t.accept["proposedDate"], t.platform_id))


def _unexplained_moves(rosters: dict[int, dict[int, set[int]]], adds: set[tuple[int, int, int]]) -> set[Move]:
    """Players on one team's roster in Week w-1 (the draft roster for Week 1) and another team's in Week w,
    with no executed add to the new team in Week w-1 or w."""
    moves = set()
    for week in sorted(w for w in rosters if w > 0):
        for src, before in rosters[week - 1].items():
            for dst, after in rosters[week].items():
                if src != dst:
                    moves |= {
                        (pid, src, dst, week)
                        for pid in before & after
                        if (pid, dst, week - 1) not in adds and (pid, dst, week) not in adds
                    }
    return moves


def _resolve_trades(files: SeasonFiles, trades: list[_Trade], moves: set[Move], team_names) -> set[Move]:
    """Give every trade its legs and effective Week; return the moves no trade claimed.

    Trades with TRADE items take the moves that match them. The rest take the one two-way swap between
    the acceptor and one other team (from teamActions when listed) in their window, settling the
    unambiguous trades first. Two trades of one team left with the same choice are assigned in the order
    they were accepted; both swaps are then real trades of that team in the same window."""
    claimed: set[Move] = set()

    for trade in trades:
        items = {
            (i["playerId"], i["fromTeamId"], i["toTeamId"])
            for r in trade.rows
            for i in r.get("items") or []
            if i["type"] == "TRADE"
        }
        if not items:
            continue
        pairs = {(src, dst) for _, src, dst in items}
        if len(pairs) != 2 or {(dst, src) for src, dst in pairs} != pairs:
            raise LoadError(
                f"Season {files.year}, Week {trade.accepted_week}: a trade's TRADE items aren't a swap between "
                "two teams in which each side receives a Player"
            )
        matched = {m for m in moves - claimed if m[:3] in items and m[3] in trade.window}
        claimed |= matched
        trade.week = min((m[3] for m in matched), default=trade.accepted_week)
        trade.legs = {(pid, src, dst, trade.week) for pid, src, dst in items}

    def swaps(trade: _Trade) -> dict[tuple[int, int], set[Move]]:
        """(Week, partner) -> moves both ways between the acceptor and that partner, among unclaimed moves."""
        a = trade.acceptor
        listed = {int(k) for k in trade.accept.get("teamActions") or {}} - {a}
        found: dict[tuple[int, int], set[Move]] = {}
        for m in moves - claimed:
            if m[3] in trade.window and a in m[1:3]:
                partner = m[2] if m[1] == a else m[1]
                if not listed or partner in listed:
                    found.setdefault((m[3], partner), set()).add(m)
        return {k: v for k, v in found.items() if {m[1] for m in v} == {a, k[1]}}

    def settle(trade: _Trade, key: tuple[int, int], legs: set[Move]) -> None:
        claimed.update(legs)
        trade.week, trade.legs = key[0], legs

    pending = [t for t in trades if t.legs is None]
    progress = True
    while progress:
        progress = False
        for trade in list(pending):
            options = swaps(trade)
            if len(options) == 1:
                settle(trade, *next(iter(options.items())))
                pending.remove(trade)
                progress = True
    for trade in pending:
        options = swaps(trade)
        if not options:
            raise LoadError(
                f"Season {files.year}, Week {trade.accepted_week}: couldn't rebuild a trade accepted by "
                f"{team_names.get(trade.acceptor, trade.acceptor)} from the weekly rosters: no two-way swap "
                f"with one other team in Week {trade.window[0]} or {trade.window[1]}"
            )
        key = min(options)
        settle(trade, key, options[key])
    return moves - claimed
