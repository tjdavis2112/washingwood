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
    has_lineups: bool

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
            has_lineups=_has_lineups(season_dir / "boxscore_w01.json"),
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
    return picks


def _draft(conn: Connection, season_id: int, files: SeasonFiles, picks: list[dict], franchise_ids) -> None:
    """Players, their NFL team this Season, and the Picks. memberId (personal) is never stored."""
    conn.execute(
        "UPDATE core.seasons SET draft_type = %s WHERE season_id = %s",
        (DRAFT_TYPES[files.settings["settings"]["draftSettings"]["type"]], season_id),
    )
    for p in picks:
        player_id = None
        if p["playerId"] != NO_PLAYER:
            espn_player = files.players[p["playerId"]]
            player_id = _upsert_player(conn, files, espn_player)
            conn.execute(
                """INSERT INTO core.player_seasons (season_id, player_id, nfl_team) VALUES (%s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (season_id, player_id, NFL_TEAMS.get(espn_player["proTeamId"])),
            )
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
                   away_franchise_id, home_points, away_points, winner_franchise_id, is_playoff, bracket,
                   playoff_round, is_championship)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (season_id, m["matchupPeriodId"], min(weeks), max(weeks), franchise_ids[home["teamId"]],
             franchise_ids[away["teamId"]] if away else None,
             home["totalPoints"], away["totalPoints"] if away else None,
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
