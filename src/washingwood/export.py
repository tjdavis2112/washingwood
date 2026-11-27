"""Export site-data documents (contract/site-data.schema.json) from core.* and stats.*.

Output is deterministic: stable ordering, no timestamps.
"""

from __future__ import annotations

from psycopg import Connection

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
    }


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
