"""Export site-data documents (contract/site-data.schema.json) from core.* and stats.*.

Output is deterministic: stable ordering, no timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import Connection

from washingwood.loader import THIRD_PLACE
from washingwood.owners import slugify


class ExportError(ValueError):
    """The loaded data can't be turned into a valid site-data document."""


def league_summary(conn: Connection) -> dict:
    seasons = conn.execute("SELECT year, team_count FROM core.seasons ORDER BY year").fetchall()
    if not seasons:
        raise ExportError("no Seasons loaded")
    latest = seasons[-1][0]
    champ = conn.execute("SELECT display_name, team_name FROM stats.champions WHERE year = %s", (latest,)).fetchall()
    if len(champ) != 1:
        raise ExportError(f"Season {latest}: expected one Champion, found {len(champ)}")
    name, team_name = champ[0]
    league_name = conn.execute(
        "SELECT l.name FROM core.leagues l JOIN core.seasons s USING (league_id) WHERE s.year = %s", (latest,)
    ).fetchone()[0]
    return {
        "leagueName": league_name,
        "seasons": [{"year": y, "teamCount": n} for y, n in seasons],
        "champion": {"owner": _owner_ref(name), "teamName": team_name, "year": latest},
    }


def trophy_shelf(conn: Connection) -> dict:
    """Every Owner, former Owners included, ordered by titles, then runner-ups (both descending), then name."""
    rows = conn.execute(
        """SELECT display_name, current_team_name, title_seasons, runner_up_seasons,
                  first_season, last_season, is_former
           FROM stats.trophy_shelf
           ORDER BY cardinality(title_seasons) DESC, cardinality(runner_up_seasons) DESC, display_name"""
    ).fetchall()
    return {
        "owners": [
            {
                "owner": _owner_ref(name),
                "currentTeamName": team,
                "titles": list(titles),
                "runnerUps": list(runner_ups),
                "firstSeason": first,
                "lastSeason": last,
                "isFormer": is_former,
            }
            for name, team, titles, runner_ups, first, last, is_former in rows
        ]
    }


def owner_index(conn: Connection) -> dict:
    """Every Owner for the Owners index, in trophy-shelf order. The regular-season record is the sum of
    the Owner's Season records in the standings (stats.owner_career), so playoffs and consolation
    Matchups are left out."""
    rows = conn.execute(
        """SELECT t.display_name, t.current_team_name, t.first_season, t.last_season, t.is_former,
                  t.title_seasons, t.runner_up_seasons, c.wins, c.losses, c.ties
           FROM stats.trophy_shelf t
           JOIN stats.owner_career c USING (owner_id)
           ORDER BY cardinality(t.title_seasons) DESC, cardinality(t.runner_up_seasons) DESC, t.display_name"""
    ).fetchall()
    return {
        "owners": [
            {
                "owner": _owner_ref(name),
                "currentTeamName": team,
                "firstSeason": first,
                "lastSeason": last,
                "isFormer": is_former,
                "titles": list(titles),
                "runnerUps": list(runner_ups),
                "regularSeason": _record(int(w), int(lost), int(tied)),
            }
            for name, team, first, last, is_former, titles, runner_ups, w, lost, tied in rows
        ]
    }


def owner_documents(conn: Connection) -> dict[str, dict]:
    """One Owner document per Owner, keyed by slug. Records, playoff record and head-to-head follow
    GLOSSARY.md (Playoff record, Playoff appearance) through stats.owner_games."""
    head = {
        owner_id: (name, team, first, last, is_former, list(titles), list(runner_ups))
        for owner_id, name, team, first, last, is_former, titles, runner_ups in conn.execute(
            """SELECT owner_id, display_name, current_team_name, first_season, last_season, is_former,
                      title_seasons, runner_up_seasons
               FROM stats.trophy_shelf"""
        ).fetchall()
    }
    seasons: dict[int, list[dict]] = {owner_id: [] for owner_id in head}
    appearances: dict[int, list[int]] = {owner_id: [] for owner_id in head}
    for owner_id, year, team, w, lost, tied, pf, pa, seed, rank, playoff_teams, is_last in conn.execute(
        """SELECT st.owner_id, st.year, st.team_name, st.wins, st.losses, st.ties, st.points_for,
                  st.points_against, st.playoff_seed, st.final_rank, s.playoff_team_count,
                  st.franchise_id = lp.franchise_id
           FROM stats.standings st
           JOIN core.seasons s       ON s.year = st.year
           JOIN stats.last_place lp ON lp.year = st.year
           ORDER BY st.year DESC"""
    ).fetchall():
        seasons[owner_id].append(
            {
                "year": year,
                "teamName": team,
                "record": _record(w, lost, tied),
                "pointsFor": float(pf),
                "pointsAgainst": float(pa),
                "playoffSeed": seed,
                "finalRank": rank,
                "podiumPlace": rank if rank <= 3 else None,
                "isLastPlace": is_last,
            }
        )
        if seed <= playoff_teams:  # Playoff appearance: a first-round bye counts
            appearances[owner_id].append(year)
    playoffs = {owner_id: _record(0, 0, 0) for owner_id in head}
    for owner_id, w, lost, tied in conn.execute(
        """SELECT owner_id, count(*) FILTER (WHERE result = 'W'), count(*) FILTER (WHERE result = 'L'),
                  count(*) FILTER (WHERE result = 'T')
           FROM stats.owner_games WHERE kind = 'playoff' GROUP BY owner_id"""
    ).fetchall():
        playoffs[owner_id] = _record(w, lost, tied)
    h2h: dict[int, list[dict]] = {owner_id: [] for owner_id in head}
    for owner_id, opp, rw, rl, rt, pw, pl, pt, meetings in conn.execute(
        """SELECT owner_id, opponent_owner_id, regular_wins, regular_losses, regular_ties,
                  playoff_wins, playoff_losses, playoff_ties, meetings
           FROM stats.head_to_head"""
    ).fetchall():
        h2h[owner_id].append(
            {
                "opponent": _owner_ref(head[opp][0]),
                "regularSeason": _record(rw, rl, rt),
                "playoffs": _record(pw, pl, pt),
                "meetings": meetings,
            }
        )

    docs = {}
    for owner_id, (name, team, first, last, is_former, titles, runner_ups) in head.items():
        rows = seasons[owner_id]
        regular = {k: sum(r["record"][k] for r in rows) for k in ("wins", "losses", "ties")}
        games = sum(regular.values())
        if not games:
            raise ExportError(f"Owner {name} has no regular-season games")
        ref = _owner_ref(name)
        docs[ref["slug"]] = {
            "owner": ref,
            "currentTeamName": team,
            "firstSeason": first,
            "lastSeason": last,
            "isFormer": is_former,
            "trophies": {
                "titles": titles,
                "runnerUps": runner_ups,
                "thirds": sorted(r["year"] for r in rows if r["podiumPlace"] == 3),
            },
            "career": {
                "regularSeason": regular,
                "playoffs": playoffs[owner_id],
                "avgPointsFor": round(sum(r["pointsFor"] for r in rows) / games, 2),
                "avgPointsAgainst": round(sum(r["pointsAgainst"] for r in rows) / games, 2),
                "playoffAppearances": sorted(appearances[owner_id]),
                "lastPlaces": sorted(r["year"] for r in rows if r["isLastPlace"]),
            },
            "seasons": rows,
            "headToHead": sorted(h2h[owner_id], key=lambda h: (-h["meetings"], h["opponent"]["name"])),
        }
    return dict(sorted(docs.items()))


def season_document(conn: Connection, year: int) -> dict:
    """One Season's document. The bracket and weekly results join in #9 and #10."""
    team_count, data_tier = conn.execute(
        "SELECT team_count, data_tier FROM core.seasons WHERE year = %s", (year,)
    ).fetchone()
    standings = _standings(conn, year, team_count)
    podium = conn.execute(
        "SELECT final_rank, owner, team_name, wins, losses, ties FROM stats.podium WHERE year = %s ORDER BY final_rank",
        (year,),
    ).fetchall()
    places = [row[0] for row in podium]
    if places != [1, 2, 3]:
        raise ExportError(f"Season {year}: expected Podium places 1, 2, 3, found {places}")
    last = conn.execute(
        "SELECT owner, team_name, wins, losses, ties, playoff_seed FROM stats.last_place WHERE year = %s", (year,)
    ).fetchone()
    # Last place is the worst regular-season seed, which must equal the team count; anything else is bad data
    if last is None or last[5] != team_count:
        seed = None if last is None else last[5]
        raise ExportError(f"Season {year}: Last place should be seed {team_count}, found seed {seed}")
    last_owner, last_team, last_w, last_l, last_t, _ = last
    return {
        "year": year,
        "teamCount": team_count,
        "dataTier": data_tier,
        "podium": [
            {"place": place, "owner": _owner_ref(owner), "teamName": team, "record": _record(w, lost, tied)}
            for place, owner, team, w, lost, tied in podium
        ],
        "lastPlace": {
            "owner": _owner_ref(last_owner),
            "teamName": last_team,
            "record": _record(last_w, last_l, last_t),
            "punishment": None,  # Punishment content arrives after v1
        },
        "scoringFormat": _scoring_format(conn, year),
        "standings": standings,
        "bracket": _bracket(conn, year),
        "weeklyResults": _weekly_results(conn, year),
        "draft": _draft(conn, year),
    }


def _draft(conn: Connection, year: int) -> dict:
    """The Season's Draft: round-1 order by Draft slot and every Pick in order (stats.draft_board)."""
    draft_type = conn.execute("SELECT draft_type FROM core.seasons WHERE year = %s", (year,)).fetchone()[0]
    rows = conn.execute(
        """SELECT overall_pick, round, round_pick, owner, team_name, draft_slot, player_name, position, nfl_team
           FROM stats.draft_board WHERE year = %s ORDER BY overall_pick""",
        (year,),
    ).fetchall()
    if not rows:
        raise ExportError(f"Season {year}: no Draft picks loaded")
    order = sorted({(slot, owner, team) for _, rnd, _, owner, team, slot, *_ in rows if rnd == 1})
    picks = [
        {
            "overall": overall,
            "round": rnd,
            "roundPick": round_pick,
            "owner": _owner_ref(owner),
            "player": None if name is None else {"name": name, "position": position, "nflTeam": nfl_team},
        }
        for overall, rnd, round_pick, owner, _, _, name, position, nfl_team in rows
    ]
    return {
        "type": draft_type,
        "rounds": max(p["round"] for p in picks),
        "order": [{"slot": slot, "owner": _owner_ref(owner), "teamName": team} for slot, owner, team in order],
        "picks": picks,
        "note": _draft_note(draft_type, sum(p["player"] is None for p in picks)),
    }


def _draft_note(draft_type: str, unrecorded: int) -> str | None:
    parts = []
    if draft_type == "offline":
        parts.append("Drafted offline and entered by hand.")
    if unrecorded:
        picks = "pick wasn't" if unrecorded == 1 else "picks weren't"
        parts.append(f"{unrecorded} {picks} recorded.")
    return " ".join(parts) or None


@dataclass(frozen=True)
class MatchupRow:
    """One core.matchups row, as the bracket and weekly results read it."""

    period: int
    weeks: list[int]
    playoff_round: str | None
    home_id: int
    away_id: int | None
    home_points: float | None
    away_points: float | None
    winner_id: int | None

    @property
    def is_bye(self) -> bool:
        return self.away_id is None

    @property
    def is_tie(self) -> bool:
        # The loader refuses unplayed Matchups, so a played one with no winner is a tie
        return not self.is_bye and self.winner_id is None


def _matchup_rows(conn: Connection, year: int, only_bracket: bool = False) -> list[MatchupRow]:
    """Matchups in ESPN's order. With only_bracket, the winners' bracket and the Third-place game."""
    where = "AND (m.bracket = 'winners' OR m.playoff_round = %s)" if only_bracket else ""
    params = (year, THIRD_PLACE) if only_bracket else (year,)
    rows = conn.execute(
        f"""SELECT m.matchup_period, m.first_week, m.last_week, m.playoff_round, m.home_franchise_id,
                   m.away_franchise_id, m.home_points, m.away_points, m.winner_franchise_id
            FROM core.matchups m JOIN core.seasons s USING (season_id)
            WHERE s.year = %s {where} ORDER BY m.matchup_period, m.matchup_id""",
        params,
    ).fetchall()
    return [
        MatchupRow(p, list(range(first, last + 1)), r, h, a, hp, ap, w) for p, first, last, r, h, a, hp, ap, w in rows
    ]


@dataclass(frozen=True)
class FranchiseInfo:
    seed: int
    owner: str
    team_name: str


def _franchises(conn: Connection, year: int) -> dict[int, FranchiseInfo]:
    """franchise_id -> seed, Owner and team name (via stats.standings, so through franchise_owners)."""
    rows = conn.execute(
        "SELECT franchise_id, playoff_seed, owner, team_name FROM stats.standings WHERE year = %s", (year,)
    ).fetchall()
    return {fid: FranchiseInfo(seed, owner, team) for fid, seed, owner, team in rows}


def _matchup_doc(row: MatchupRow, franchises: dict[int, FranchiseInfo], *, in_bracket: bool) -> dict:
    """A Matchup in the contract's shape. In the bracket, sides carry seeds, the better seed is listed
    first, and a bye shows no score (no game). In weekly results ESPN's order and bye score are kept."""
    sides = [(row.home_id, row.home_points), (row.away_id, row.away_points)]
    if in_bracket and not row.is_bye and franchises[row.away_id].seed < franchises[row.home_id].seed:
        sides.reverse()  # the better seed is listed first, whichever side ESPN called home
    (home_id, home_pts), (away_id, away_pts) = sides
    if in_bracket and row.is_bye:
        home_pts = None

    def side(fid, points):
        f = franchises[fid]
        doc = {
            "owner": _owner_ref(f.owner),
            "teamName": f.team_name,
            "score": None if points is None else float(points),
        }
        return {"seed": f.seed, **doc} if in_bracket else doc

    return {
        "home": side(home_id, home_pts),
        "away": None if row.is_bye else side(away_id, away_pts),
        "winner": None if row.is_bye or row.is_tie else ("home" if row.winner_id == home_id else "away"),
        "isTie": row.is_tie,
        "isBye": row.is_bye,
    }


def _weekly_results(conn: Connection, year: int) -> list[dict]:
    """Every Matchup period in order, each with all of its Matchups (regular season, playoffs and
    consolation games) in ESPN's order. Scores are ESPN's Matchup totals: no manual adjustments.
    A team on a bye shows the points ESPN recorded for it that Week."""
    franchises = _franchises(conn, year)
    periods: dict[int, dict] = {}
    for row in _matchup_rows(conn, year):
        p = periods.setdefault(row.period, {"matchupPeriod": row.period, "weeks": row.weeks, "matchups": []})
        p["matchups"].append(_matchup_doc(row, franchises, in_bracket=False))
    return [periods[p] for p in sorted(periods)]


# core.matchups.playoff_round -> round name shown on the site
ROUND_NAMES = {"quarterfinal": "Quarterfinals", "semifinal": "Semifinals", "final": "Championship"}


def _bracket(conn: Connection, year: int) -> dict:
    """Winners' bracket rounds plus the Third-place game. Consolation games (5th place and the
    losers' ladder) aren't part of it. Scores are ESPN's Matchup totals, so a two-week round
    shows its combined score."""
    franchises = _franchises(conn, year)
    rounds: dict[int, dict] = {}
    third = None
    for row in _matchup_rows(conn, year, only_bracket=True):
        matchup = _matchup_doc(row, franchises, in_bracket=True)
        if row.playoff_round == THIRD_PLACE:
            third = {"matchupPeriod": row.period, "weeks": row.weeks, "matchup": matchup}
            continue
        name = ROUND_NAMES.get(row.playoff_round) or (row.playoff_round or "Playoffs").title()
        rounds.setdefault(row.period, {"name": name, "matchupPeriod": row.period, "weeks": row.weeks, "matchups": []})
        rounds[row.period]["matchups"].append(matchup)
    if third is None or not rounds:
        raise ExportError(f"Season {year}: the bracket has no rounds or no Third-place game")
    final = rounds[max(rounds)]
    if len(final["matchups"]) != 1:
        raise ExportError(f"Season {year}: the championship round has {len(final['matchups'])} Matchups, not 1")
    for r in rounds.values():
        r["matchups"].sort(key=lambda m: m["home"]["seed"])
    return {"rounds": [rounds[p] for p in sorted(rounds)], "thirdPlaceGame": third}


# Display order and labels for the Scoring format tab (keys: core.seasons.scoring_rules)
KEY_VALUE_LABELS = [
    ("pass_yds", "Passing yard"),
    ("pass_td", "Passing TD"),
    ("pass_int", "Interception thrown"),
    ("rush_yds", "Rushing yard"),
    ("rush_td", "Rushing TD"),
    ("rec", "Reception"),
    ("rec_yds", "Receiving yard"),
    ("rec_td", "Receiving TD"),
    ("fum_lost", "Fumble lost"),
]
SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "OP", "D/ST", "K", "BE", "IR"]


def _scoring_format(conn: Connection, year: int) -> dict:
    label, reception, te_premium, rules, slots = conn.execute(
        "SELECT scoring_label, reception_points, te_premium, scoring_rules, roster_slots FROM core.seasons "
        "WHERE year = %s",
        (year,),
    ).fetchone()
    rules, slots = rules or {}, slots or {}
    ordered_slots = sorted(slots, key=lambda s: (SLOT_ORDER.index(s) if s in SLOT_ORDER else len(SLOT_ORDER), s))
    return {
        "label": label,
        "receptionPoints": float(reception),
        "tePremium": float(te_premium or 0),
        "keyValues": [{"label": text, "points": float(rules[key])} for key, text in KEY_VALUE_LABELS if key in rules],
        "rosterSlots": [{"slot": s, "count": slots[s]} for s in ordered_slots if slots[s]],
    }


def _standings(conn: Connection, year: int, team_count: int) -> list[dict]:
    rows = conn.execute(
        """SELECT final_rank, owner, team_name, wins, losses, ties, points_for, points_against, playoff_seed
           FROM stats.standings WHERE year = %s ORDER BY final_rank""",
        (year,),
    ).fetchall()
    if [r[0] for r in rows] != list(range(1, team_count + 1)):
        raise ExportError(f"Season {year}: final ranks should be 1..{team_count}, found {[r[0] for r in rows]}")
    return [
        {
            "rank": rank,
            "owner": _owner_ref(owner),
            "teamName": team,
            "record": _record(w, lost, tied),
            "pointsFor": float(pf),
            "pointsAgainst": float(pa),
            "playoffSeed": seed,
        }
        for rank, owner, team, w, lost, tied, pf, pa, seed in rows
    ]


def _owner_ref(name: str) -> dict:
    return {"slug": slugify(name), "name": name}


def _record(wins: int, losses: int, ties: int) -> dict:
    return {"wins": wins, "losses": losses, "ties": ties}
