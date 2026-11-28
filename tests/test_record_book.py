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


def test_season_records_rank_points_per_game_not_total(archive, owners, tmp_path, pg_dsn):
    # 2018 (13 games): Quinn scores 1499. 2020 (14 games): a +50 adjustment makes Quinn's total
    # 1549, the highest, but only 110.64 per game
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    season(2020, adjustments={"quinn": 50.0}).write(archive)

    season_doc = record_book(archive, owners, tmp_path, pg_dsn)["season"]

    top = season_doc["mostPointsFor"]
    # Every 2018 Franchise (lowest 1490 / 13 = 114.62) out-scores 2020 Quinn per game, so the season
    # with the highest total (1549) misses the top 10
    assert [r["year"] for r in top] == [2018] * 10
    assert (top[0]["owner"]["slug"], top[0]["pointsFor"], top[0]["games"], top[0]["pointsPerGame"]) == (
        "quinn-harrow",
        1499.0,
        13,
        115.31,
    )
    assert season_doc["fewestPointsFor"][0]["pointsPerGame"] == round(1488 / 14, 2)  # Jory, 2020
    assert season_doc["mostPointsAgainst"][0]["pointsAgainstPerGame"] == round(1410 / 13, 2)  # Wren, 2018
    assert all(len(v) == 10 for v in season_doc.values())


def test_playoff_and_consolation_games_do_not_count(archive, owners, tmp_path, pg_dsn):
    # Quinn (seed 1) plays playoff Matchups, Jory (seed 12) consolation ones; neither adds games
    season(2020).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    best = doc["season"]["bestWinPct"][0]
    assert (best["owner"]["slug"], best["record"], best["games"], best["winPct"]) == (
        "quinn-harrow",
        {"wins": 13, "losses": 1, "ties": 0},
        14,
        0.9286,
    )
    assert doc["season"]["worstWinPct"][0]["owner"]["slug"] == "jory-paxton"
    assert {r["games"] for r in doc["allTime"]} == {14}


def test_all_time_includes_owners_who_left(archive, owners, tmp_path, pg_dsn):
    # Nell is seed 10 (last) in 2018 and gone by 2020
    Season2018Style(2018, [team(k) for k in [*SEED_ORDER[:9], "nell"]]).write(archive)
    season(2020).write(archive)

    all_time = record_book(archive, owners, tmp_path, pg_dsn)["allTime"]

    assert len(all_time) == 13
    (nell,) = [r for r in all_time if r["owner"] == owner("nell")]
    assert nell == {
        "owner": owner("nell"),
        "seasons": 1,
        "record": {"wins": 3, "losses": 10, "ties": 0},
        "games": 13,
        "winPct": 0.2308,
        "pointsFor": 1490.0,
        "pointsPerGame": 114.62,
        "lastPlaces": 1,
    }
    (quinn,) = [r for r in all_time if r["owner"] == owner("quinn")]
    assert (quinn["seasons"], quinn["record"]["wins"], quinn["games"], quinn["pointsFor"]) == (2, 25, 27, 2998.0)
    assert (quinn["winPct"], quinn["pointsPerGame"], quinn["lastPlaces"]) == (0.9259, 111.04, 0)
    # Wins descending, then name
    assert [r["record"]["wins"] for r in all_time] == sorted((r["record"]["wins"] for r in all_time), reverse=True)


def test_season_record_ties_go_to_the_earlier_season_then_name(archive, owners, tmp_path, pg_dsn):
    # Two identical Seasons, and a +1 adjustment puts Pell level with Quinn (1499) in each
    season(2020, adjustments={"pell": 1.0}).write(archive)
    season(2021, adjustments={"pell": 1.0}).write(archive)

    top = record_book(archive, owners, tmp_path, pg_dsn)["season"]["mostPointsFor"][:4]

    assert [(r["year"], r["owner"]["slug"]) for r in top] == [
        (2020, "pell-vantor"),
        (2020, "quinn-harrow"),
        (2021, "pell-vantor"),
        (2021, "quinn-harrow"),
    ]
