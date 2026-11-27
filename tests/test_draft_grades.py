"""Seam 1 for Season points, Value over slot and Draft grades (#28).

Fixture default: Season points fall with the overall pick (400 - 3 x overall), so every Pick's Value
over slot is 0 unless a test overrides some points. All data is invented.

GLOSSARY: Value over slot = overall pick - rank by Season points among that Season's drafted Picks
(ties share the better rank). Draft grade = sum of a Franchise's Value over slot, ranked in the Season.
Positional finish = rank by Season points among every pool Player at that position.
"""

import json

import pytest
from espn_fixture import PEOPLE, Season2018Style, team
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate
from washingwood.loader import LoadError


def export_season(archive, owners, tmp_path, pg_dsn, year):
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "seasons" / f"{year}.json").read_text(encoding="utf-8"))
    validate(doc, "season")
    return doc["draft"]


@pytest.fixture
def graded(archive, owners, tmp_path, pg_dsn):
    # 12 teams x 3 rounds. Pick 36 (Quinn's last, a K) scores 500: the best of the Season.
    # Pick 2 ties pick 1 on 397. An undrafted K scores 600, above every drafted K.
    season(2021, player_points={5036: 500.0, 5002: 397.0}, undrafted={8001: (5, 600.0)}).write(archive)
    return export_season(archive, owners, tmp_path, pg_dsn, 2021)


def test_value_over_slot_is_overall_pick_minus_points_rank_with_ties_sharing_the_better_rank(graded):
    vos = {p["overall"]: p["valueOverSlot"] for p in graded["picks"]}
    # Ranks: pick 36 -> 1; picks 1 and 2 tie -> 2; pick k (3..35) -> k + 1
    assert vos[36] == 35
    assert vos[1] == -1
    assert vos[2] == 0
    assert all(vos[k] == -1 for k in range(3, 36))


def test_picks_carry_season_points_and_positional_finish_against_undrafted_players(graded):
    picks = {p["overall"]: p for p in graded["picks"]}
    assert picks[36]["points"] == 500.0
    assert picks[1]["points"] == 397.0
    # Ks are picks 6, 12, ..., 36. The undrafted K (600) is K1, so pick 36 is K2 and pick 6 (382) K3.
    assert picks[36]["positionalFinish"] == 2
    assert picks[6]["positionalFinish"] == 3
    assert picks[12]["positionalFinish"] == 4


def test_draft_grades_sum_value_over_slot_and_rank_within_the_season(graded):
    grades = graded["grades"]
    assert len(grades) == 12
    # Quinn (slot 12): picks 12, 13, 36 -> -1 - 1 + 35 = 33. Cass (slot 2): picks 2, 23, 26 -> 0 - 1 - 1 = -2.
    # Everyone else: three picks at -1 -> -3, tied for 3rd.
    assert grades[0] == {
        "rank": 1,
        "owner": owner("quinn"),
        "teamName": PEOPLE["quinn"][1],
        "total": 33,
        "best": {
            "overall": 36,
            "round": 3,
            "roundPick": 12,
            "player": {"name": "Fixture Player 036", "position": "K", "nflTeam": "CIN"},
            "valueOverSlot": 35,
        },
        "worst": {
            "overall": 12,
            "round": 1,
            "roundPick": 12,
            "player": {"name": "Fixture Player 012", "position": "K", "nflTeam": "KC"},
            "valueOverSlot": -1,
        },
    }
    assert (grades[1]["rank"], grades[1]["owner"], grades[1]["total"]) == (2, owner("cass"), -2)
    rest = grades[2:]
    assert {g["rank"] for g in rest} == {3} and {g["total"] for g in rest} == {-3}
    # Ties are listed by Owner name
    assert [g["owner"]["name"] for g in rest] == sorted(g["owner"]["name"] for g in rest)


def test_an_unrecorded_pick_has_no_points_and_is_left_out_of_the_ranking(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], draft_type="OFFLINE", unrecorded_picks={20}).write(
        archive
    )
    draft = export_season(archive, owners, tmp_path, pg_dsn, 2018)
    picks = {p["overall"]: p for p in draft["picks"]}
    assert (picks[20]["points"], picks[20]["positionalFinish"], picks[20]["valueOverSlot"]) == (None, None, None)
    # Without pick 20, picks 21..30 move up one rank: Value over slot +1 each
    assert [picks[k]["valueOverSlot"] for k in (1, 19, 21, 30)] == [0, 0, 1, 1]


def test_a_drafted_player_without_a_season_total_in_the_pool_fails_the_build(archive, owners, tmp_path, pg_dsn):
    season(2021, pool_without_points={5003}).write(archive)
    with pytest.raises(LoadError, match=r"Season 2021: .*5003.*no Season points"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_projected_and_weekly_rows_are_ignored(graded):
    # The fixture pool also has a projected season row (999) and a week-1 row (12.5) per Player
    assert all(p["points"] not in (999.0, 12.5) for p in graded["picks"])
