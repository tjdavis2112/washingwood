"""Seam 1 for Season points, Value over slot and Draft grades (#28; positional Value over slot).

Fixture: 12 teams x 3 rounds. Positions cycle by overall pick (RB, WR, QB, TE, D/ST, K), so each
position has 6 Picks: K at 6, 12, 18, 24, 30, 36; WR at 2, 8, 14, 20, 26, 32. Default Season points
fall with the overall pick (400 - 3 x overall), so every Pick's Value over slot is 0 unless a test
overrides some points. All data is invented.

GLOSSARY: Value over slot = the Pick's order among that Season's Picks at its position, minus its
finish by Season points among the drafted Players at that position (ties share the better finish).
Draft grade = sum of a Franchise's Value over slot, ranked in the Season. Positional finish (shown on
each Pick) = rank by Season points among every pool Player at that position, drafted or not.

Round-1 order is worst seed first: slot 1 Jory, 2 Cass, 3 Wren, 4 Abel, 5 Ines, 6 Marlo, 7 Lyle,
8 Tamsin, 9 Rue, 10 Odie, 11 Pell, 12 Quinn.
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


def test_draft_grades_sum_value_over_slot_and_rank_within_the_season(graded):
    grades = graded["grades"]
    assert len(grades) == 12
    # Quinn: 12 (K, -1) + 13 (RB, 0) + 36 (K, +5) = +4. Tamsin: 8 (WR, +1) + 17 + 32 = +1.
    assert grades[0] == {
        "rank": 1,
        "owner": owner("quinn"),
        "teamName": PEOPLE["quinn"][1],
        "total": 4,
        "best": {
            "overall": 36,
            "round": 3,
            "roundPick": 12,
            "player": {"name": "Fixture Player 036", "position": "K", "nflTeam": "CIN"},
            "valueOverSlot": 5,
        },
        "worst": {
            "overall": 12,
            "round": 1,
            "roundPick": 12,
            "player": {"name": "Fixture Player 012", "position": "K", "nflTeam": "KC"},
            "valueOverSlot": -1,
        },
    }
    assert (grades[1]["rank"], grades[1]["owner"], grades[1]["total"]) == (2, owner("tamsin"), 1)
    # Seven Franchises without a K that moved: 0, tied 3rd, listed by name
    tied = grades[2:9]
    assert {(g["rank"], g["total"]) for g in tied} == {(3, 0)}
    assert [g["owner"]["name"] for g in tied] == sorted(g["owner"]["name"] for g in tied)
    # Jory (24) and Lyle (18) each lost one K place; Marlo (6 and 30) lost two
    assert [(g["rank"], g["owner"]["slug"], g["total"]) for g in grades[9:]] == [
        (10, owner("jory")["slug"], -1),
        (10, owner("lyle")["slug"], -1),
        (12, owner("marlo")["slug"], -2),
    ]


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
