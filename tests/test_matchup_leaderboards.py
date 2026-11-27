"""Seam 1 for Matchup leaderboards (#38). All data is invented.

Fixture scoring (tests/espn_fixture.py): a home win is 120.5-101.25 (Margin 19.25) and an away win
99.75-118.0 (Margin 18.25). Regular-season home sides always win; in the playoffs the better seed is
home and wins unless the other side is in `upsets`.

Scenario:
- 2018 (10 teams, two-week playoff rounds): seed 4 Rue upsets seed 1 Quinn in the semifinal. Two-week
  rounds aren't Counted Matchups, so none of 2018's playoff games may appear.
- 2021 (12 teams): seed 5 Tamsin wins three playoff games as the away side (periods 15, 16, 17 against
  seeds 4, 1 and 2). Period 3's first Matchup is set to 180-60, period 5's first is a 110-110 tie. A
  losers' consolation game (period 15) is set to 250-20 and the Third-place game (period 17) to
  200.5-200.0; neither is counted, so neither may appear.
"""

import json

import pytest
from espn_fixture import PEOPLE, Season2018Style, team
from test_build import SEED_ORDER, season

from washingwood.build import build
from washingwood.contract import validate
from washingwood.owners import slugify

EXCLUDED_SCORES = {250.0, 20.0, 200.5, 200.0}


@pytest.fixture
def boards(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], upsets={"rue"}).write(archive)
    season(
        2021,
        upsets={"tamsin"},
        tie_period=5,
        scores={(3, 0): (180.0, 60.0), (15, 4): (250.0, 20.0), (17, 2): (200.5, 200.0)},
    ).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "matchups.json").read_text(encoding="utf-8"))
    validate(doc, "matchups")
    return doc["leaderboards"]


def ref(key):
    name = PEOPLE[key][0]
    return {"slug": slugify(name), "name": name}


def all_rows(boards):
    return [r for rows in boards.values() for r in rows]


def scores_in(row):
    if "team" in row:
        return {row["team"]["score"], row["opponent"]["score"]}
    return {row["winner"]["score"], row["loser"]["score"]}


def test_every_leaderboard_has_ten_rows_with_a_scoring_format(boards):
    assert set(boards) == {
        "blowouts",
        "closestGames",
        "highestScores",
        "lowestScores",
        "playoffUpsets",
        "projectionUpsets",
    }
    for name in ("blowouts", "closestGames", "highestScores", "lowestScores"):
        assert len(boards[name]) == 10, name
    assert all(r["scoringFormat"] == "PPR" for r in all_rows(boards))


def test_consolation_third_place_and_two_week_games_are_not_counted(boards):
    for row in all_rows(boards):
        assert not (scores_in(row) & EXCLUDED_SCORES), row
        assert not (row["year"] == 2018 and row["matchupPeriod"] >= 14), row  # two-week rounds
        assert len(row["weeks"]) == 1


def test_biggest_blowout_and_both_sides_of_it_on_the_score_lists(boards):
    top = boards["blowouts"][0]
    assert (top["year"], top["matchupPeriod"], top["weeks"], top["kind"]) == (2021, 3, [3], "regular")
    assert (top["winner"]["score"], top["loser"]["score"], top["margin"], top["isTie"]) == (180.0, 60.0, 120.0, False)
    assert top["winner"]["seed"] is None  # regular season: no seeds
    # The same Matchup tops highest (180) and lowest (60), one side each
    high, low = boards["highestScores"][0], boards["lowestScores"][0]
    assert (high["year"], high["matchupPeriod"], high["team"]["score"], high["result"]) == (2021, 3, 180.0, "win")
    assert (low["year"], low["matchupPeriod"], low["team"]["score"], low["result"]) == (2021, 3, 60.0, "loss")
    assert high["team"]["owner"] == low["opponent"]["owner"]


def test_closest_games_start_with_the_tie_then_the_smallest_margins_by_season_and_week(boards):
    closest = boards["closestGames"]
    assert (closest[0]["year"], closest[0]["matchupPeriod"], closest[0]["isTie"], closest[0]["margin"]) == (
        2021,
        5,
        True,
        0.0,
    )
    # Then Tamsin's three away wins (Margin 18.25) in Week order, then the 19.25 games from 2018 Week 1
    assert [(r["matchupPeriod"], r["margin"], r["kind"]) for r in closest[1:4]] == [
        (15, 18.25, "playoff"),
        (16, 18.25, "playoff"),
        (17, 18.25, "playoff"),
    ]
    assert all(r["winner"]["owner"] == ref("tamsin") for r in closest[1:4])
    assert (closest[4]["year"], closest[4]["matchupPeriod"], closest[4]["margin"]) == (2018, 1, 19.25)


def test_score_lists_break_ties_by_season_week_then_owner_name(boards):
    rest = boards["highestScores"][1:]
    assert {r["team"]["score"] for r in rest} == {120.5}
    keys = [(r["year"], r["matchupPeriod"], r["team"]["owner"]["name"]) for r in rest]
    assert keys == sorted(keys)


def test_playoff_upsets_rank_by_seed_gap_and_skip_two_week_rounds(boards):
    upsets = boards["playoffUpsets"]
    assert [(r["year"], r["matchupPeriod"], r["seedGap"]) for r in upsets] == [
        (2021, 16, 4),
        (2021, 17, 3),
        (2021, 15, 1),
    ]
    top = upsets[0]
    assert (top["winner"]["owner"], top["winner"]["seed"], top["loser"]["owner"], top["loser"]["seed"]) == (
        ref("tamsin"),
        5,
        ref("quinn"),
        1,
    )
    assert top["kind"] == "playoff" and top["margin"] == 18.25
