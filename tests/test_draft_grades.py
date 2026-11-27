"""Seam 1 for Season points, Value over slot and Draft grades (#28; positional Value over slot).

Fixture: 12 teams x 3 rounds. Positions cycle by overall pick (RB, WR, QB, TE, D/ST, K), so each
position has 6 Picks: K at 6, 12, 18, 24, 30, 36; WR at 2, 8, 14, 20, 26, 32. Default Season points
fall with the overall pick (400 - 3 x overall), so every Pick's Value over slot is 0 unless a test
overrides some points. All data is invented.

GLOSSARY: Value over slot = the Pick's order among that Season's Picks at its position, minus its
finish by Season points among the drafted Players at that position (ties share the better finish).
Points over expected = Points above replacement (floored at 0) minus the Round's mean across every
Season. Draft grade = sum of a Franchise's Points over expected, ranked in the Season. Positional
finish (shown on each Pick) = rank by Season points among every pool Player at that position.
tests/draft_examples.py is the plain-Python reference the SQL is checked against.

Round-1 order is worst seed first: slot 1 Jory, 2 Cass, 3 Wren, 4 Abel, 5 Ines, 6 Marlo, 7 Lyle,
8 Tamsin, 9 Rue, 10 Odie, 11 Pell, 12 Quinn.
"""

import json

import draft_examples
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
    # Pick 36 (Quinn's last, the 6th K taken) scores 500: the best K. Pick 8 (the 2nd WR taken) ties
    # pick 2 (the 1st WR) on 394. An undrafted K scores 600, above every drafted K.
    season(2021, player_points={5036: 500.0, 5008: 394.0}, undrafted={8001: (5, 600.0)}).write(archive)
    return export_season(archive, owners, tmp_path, pg_dsn, 2021)


def test_value_over_slot_compares_a_pick_only_with_picks_at_its_position(graded):
    vos = {p["overall"]: p["valueOverSlot"] for p in graded["picks"]}
    # Ks: pick 36 taken 6th, finished 1st among drafted Ks -> +5; the other five each finish one lower -> -1
    assert vos[36] == 5
    assert [vos[k] for k in (6, 12, 18, 24, 30)] == [-1] * 5
    # WRs: picks 2 and 8 tie for 1st (the better finish is shared): pick 2 -> 1 - 1 = 0, pick 8 -> 2 - 1 = +1
    assert (vos[2], vos[8], vos[14]) == (0, 1, 0)
    # Every other position is untouched
    assert all(vos[k] == 0 for k in range(1, 37) if k % 6 not in (0, 2))


def test_the_undrafted_player_counts_for_positional_finish_but_not_for_value(graded):
    picks = {p["overall"]: p for p in graded["picks"]}
    assert picks[36]["points"] == 500.0
    # Shown finish is league-wide: the undrafted K (600) is K1, so pick 36 is K2 and pick 6 (382) K3
    assert (picks[36]["positionalFinish"], picks[6]["positionalFinish"], picks[12]["positionalFinish"]) == (2, 3, 4)
    # ...but Value over slot ranks among drafted Ks only, where pick 36 is 1st
    assert picks[36]["valueOverSlot"] == 5


def test_replacement_level_is_team_count_times_starters_or_the_last_player(graded):
    # Fixture lineup: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K; 12 teams. RB and WR get half the FLEX:
    # 12 x 2.5 = 30. Every position has fewer Players than its finish, so the last one sets the level:
    # the 6th drafted RB (307), the undrafted 50-point WR, and the 5th K (310; pick 36 now scores 500).
    assert graded["replacement"] == [
        {"position": "D/ST", "finish": 12, "points": 295.0},
        {"position": "K", "finish": 12, "points": 310.0},
        {"position": "QB", "finish": 12, "points": 301.0},
        {"position": "RB", "finish": 30, "points": 307.0},
        {"position": "TE", "finish": 12, "points": 298.0},
        {"position": "WR", "finish": 30, "points": 50.0},
    ]


def test_points_over_expected_floors_below_replacement_and_compares_with_the_round(archive, owners, tmp_path, pg_dsn):
    # 25 undrafted RBs on 200 tie at RB6 (filling RB6..RB30), so finish 30 scores 200. Pick 31 (the 6th RB,
    # round 3) scores 150: below replacement, so 0 above it rather than -50.
    undrafted = {8100 + i: (2, 200.0) for i in range(25)}
    season(2021, player_points={5031: 150.0}, undrafted=undrafted).write(archive)
    draft = export_season(archive, owners, tmp_path, pg_dsn, 2021)
    assert {"position": "RB", "finish": 30, "points": 200.0} in draft["replacement"]
    picks = {p["overall"]: p for p in draft["picks"]}
    round3 = [p for p in draft["picks"] if p["round"] == 3]
    expected = draft_examples.round_expectations([draft])[3]
    assert draft_examples.points_above_replacement(picks[31], draft["replacement"]) == 0
    assert picks[31]["pointsOverExpected"] == round(-expected)
    # The Round's expectation is the mean over its 12 Picks, so its values sum to about 0
    assert abs(sum(p["pointsOverExpected"] for p in round3)) <= len(round3) / 2


def test_points_over_expected_and_grades_match_the_reference(graded):
    poe = draft_examples.points_over_expected(graded, draft_examples.round_expectations([graded]))
    assert {p["overall"]: p["pointsOverExpected"] for p in graded["picks"]} == poe
    assert graded["grades"] == draft_examples.grades(graded, poe)


def test_draft_grades_sum_points_over_expected_and_rank_within_the_season(graded):
    grades = graded["grades"]
    assert len(grades) == 12
    by_slug = {g["owner"]["slug"]: g for g in grades}
    for slug, g in by_slug.items():
        mine = [p for p in graded["picks"] if p["owner"]["slug"] == slug]
        assert g["total"] == sum(p["pointsOverExpected"] for p in mine)
        assert g["best"]["pointsOverExpected"] == max(p["pointsOverExpected"] for p in mine)
        assert g["worst"]["pointsOverExpected"] == min(p["pointsOverExpected"] for p in mine)
    assert [g["rank"] for g in grades] == sorted(g["rank"] for g in grades)
    assert [g["total"] for g in grades] == sorted((g["total"] for g in grades), reverse=True)
    # Quinn's pick 36 (K, 500 points, 190 above the K replacement) is the Season's biggest return in round 3
    quinn = by_slug[owner("quinn")["slug"]]
    assert quinn["best"]["overall"] == 36
    assert quinn["best"]["player"] == {"name": "Fixture Player 036", "position": "K", "nflTeam": "CIN"}
    assert quinn["teamName"] == PEOPLE["quinn"][1]


def test_an_unrecorded_pick_has_no_points_and_is_left_out_of_its_positions_order(archive, owners, tmp_path, pg_dsn):
    # 10 teams x 3 rounds. Pick 20 is the 4th WR taken (WRs at 2, 8, 14, 20, 26) and isn't recorded.
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], draft_type="OFFLINE", unrecorded_picks={20}).write(
        archive
    )
    draft = export_season(archive, owners, tmp_path, pg_dsn, 2018)
    picks = {p["overall"]: p for p in draft["picks"]}
    assert (picks[20]["points"], picks[20]["positionalFinish"], picks[20]["valueOverSlot"]) == (None, None, None)
    # Pick 26 is then the 4th recorded WR and finishes 4th among them: 0, not shifted
    assert picks[26]["valueOverSlot"] == 0
    assert {p["valueOverSlot"] for p in draft["picks"] if p["player"]} == {0}


def test_a_drafted_player_without_a_season_total_in_the_pool_fails_the_build(archive, owners, tmp_path, pg_dsn):
    season(2021, pool_without_points={5003}).write(archive)
    with pytest.raises(LoadError, match=r"Season 2021: .*5003.*no Season points"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_projected_and_weekly_rows_are_ignored(graded):
    # The fixture pool also has a projected season row (999) and a week-1 row (12.5) per Player
    assert all(p["points"] not in (999.0, 12.5) for p in graded["picks"])
