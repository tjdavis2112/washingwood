"""Export site-data documents (contract/site-data.schema.json) from core.* and stats.*.

Output is deterministic: stable ordering, no timestamps.
"""

from __future__ import annotations

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
    }


# core.matchups.playoff_round -> round name shown on the site
ROUND_NAMES = {"quarterfinal": "Quarterfinals", "semifinal": "Semifinals", "final": "Championship"}


def _bracket(conn: Connection, year: int) -> dict:
    """Winners' bracket rounds plus the Third-place game. Consolation games (5th place and the
    losers' ladder) aren't part of it. Scores are ESPN's Matchup totals, so a two-week round
    shows its combined score."""
    rows = conn.execute(
        """SELECT m.matchup_period, m.first_week, m.last_week, m.playoff_round,
                  m.home_franchise_id, m.away_franchise_id, m.home_points, m.away_points, m.winner_franchise_id
           FROM core.matchups m JOIN core.seasons s USING (season_id)
           WHERE s.year = %s AND (m.bracket = 'winners' OR m.playoff_round = %s)
           ORDER BY m.matchup_period""",
        (year, THIRD_PLACE),
    ).fetchall()
    standing_by_franchise = {
        fid: (seed, owner, team)
        for fid, seed, owner, team in conn.execute(
            "SELECT franchise_id, playoff_seed, owner, team_name FROM stats.standings WHERE year = %s", (year,)
        ).fetchall()
    }

    def side(fid, points, is_bye):
        seed, owner, team = standing_by_franchise[fid]
        return {"seed": seed, "owner": _owner_ref(owner), "teamName": team, "score": None if is_bye else float(points)}

    def matchup(home_id, away_id, home_pts, away_pts, winner_id):
        is_bye = away_id is None
        sides = [(home_id, home_pts), (away_id, away_pts)]
        if not is_bye and standing_by_franchise[away_id][0] < standing_by_franchise[home_id][0]:
            sides.reverse()  # the better seed is listed first, whichever side ESPN called home
        (h_id, h_pts), (a_id, a_pts) = sides
        is_tie = not is_bye and winner_id is None
        winner = None if is_bye or is_tie else ("home" if winner_id == h_id else "away")
        return {
            "home": side(h_id, h_pts, is_bye),
            "away": None if is_bye else side(a_id, a_pts, False),
            "winner": winner,
            "isTie": is_tie,
            "isBye": is_bye,
        }

    rounds: dict[int, dict] = {}
    third = None
    for period, first, last, label, home_id, away_id, home_pts, away_pts, winner_id in rows:
        weeks = list(range(first, last + 1))
        game = matchup(home_id, away_id, home_pts, away_pts, winner_id)
        if label == THIRD_PLACE:
            third = {"matchupPeriod": period, "weeks": weeks, "matchup": game}
            continue
        name = ROUND_NAMES.get(label) or (label or "Playoffs").title()
        rounds.setdefault(period, {"name": name, "matchupPeriod": period, "weeks": weeks, "matchups": []})
        rounds[period]["matchups"].append(game)
    if third is None or not rounds:
        raise ExportError(f"Season {year}: the bracket has no rounds or no Third-place game")
    final = rounds[max(rounds)]
    if len(final["matchups"]) != 1:
        raise ExportError(f"Season {year}: the championship round has {len(final['matchups'])} Matchups, not 1")
    for r in rounds.values():
        r["matchups"].sort(key=lambda g: g["home"]["seed"])
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
