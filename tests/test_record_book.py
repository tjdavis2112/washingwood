"""Seam 1 for the Record Book (#49). All data is invented.

Fixture rule (tests/espn_fixture.py): seed s finishes (regular periods - s) wins and s losses, with
1500 - s points for, so the last seed in the team order is Last place.
"""

import json

from espn_fixture import PEOPLE, Season2018Style, team
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate


def record_book(archive, owners, tmp_path, pg_dsn) -> dict:
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "record-book.json").read_text(encoding="utf-8"))
    validate(doc, "recordBook")
    return doc


def last(key, year, wins, losses, points_for, scoring):
    return {
        "year": year,
        "owner": owner(key),
        "teamName": PEOPLE[key][1],
        "record": {"wins": wins, "losses": losses, "ties": 0},
        "pointsFor": points_for,
        "scoringFormat": scoring,
    }


def test_last_place_history_and_tally(archive, owners, tmp_path, pg_dsn):
    # 2018 style (10 teams, 13 regular periods): Jory is seed 10, the worst regular season
    Season2018Style(2018, [team(k) for k in SEED_ORDER[2:12]]).write(archive)
    # 2020 style (12 teams, 14 regular periods): Jory last again, with a TE premium
    season(2020, te_premium=True).write(archive)
    # 2021: Cass and Jory swap, so Cass is last
    season(2021, order=[*SEED_ORDER[:10], "jory", "cass"]).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    assert doc["lastPlace"]["seasons"] == [
        last("cass", 2021, 2, 12, 1488.0, "PPR"),
        last("jory", 2020, 2, 12, 1488.0, "PPR + TE premium"),
        last("jory", 2018, 3, 10, 1490.0, "PPR"),
    ]
    # Count descending, then name; Seasons oldest first
    assert doc["lastPlace"]["tally"] == [
        {"owner": owner("jory"), "count": 2, "years": [2018, 2020]},
        {"owner": owner("cass"), "count": 1, "years": [2021]},
    ]


def test_tally_ties_are_ordered_by_name(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)
    season(2021, order=[*SEED_ORDER[:10], "jory", "cass"]).write(archive)

    tally = record_book(archive, owners, tmp_path, pg_dsn)["lastPlace"]["tally"]

    names = [e["owner"]["name"] for e in tally]
    assert names == sorted(names)
    assert [e["count"] for e in tally] == [1, 1]
