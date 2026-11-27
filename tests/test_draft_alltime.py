"""Seam 1 for Draft grades on Owner pages and the all-time Draft tables (#29). All data is invented.

Two Seasons. 2021 is test_draft_grades.py's scenario without the undrafted K: pick 36 (Quinn's last,
the 6th K taken) scores 500 and pick 8 (the 2nd WR) ties pick 2 (the 1st WR). Value over slot: +5 for
pick 36, -1 for the other five Ks (6, 12, 18, 24, 30), +1 for pick 8, 0 for everything else. Draft
grades: Quinn 1st (+4), Tamsin 2nd (+1), seven tied 3rd (0), Jory and Lyle tied 10th (-1), Marlo 12th
(-2). 2022 uses default points: every Pick 0, every Franchise tied 1st.
"""

import json

import pytest
from espn_fixture import PEOPLE
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate


@pytest.fixture
def export(archive, owners, tmp_path, pg_dsn):
    season(2021, player_points={5036: 500.0, 5008: 394.0}).write(archive)
    season(2022).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)

    def load(name, kind):
        doc = json.loads((out / name).read_text(encoding="utf-8"))
        validate(doc, kind)
        return doc

    return load


def test_owner_draft_seasons_carry_their_grade_and_pick_values(export):
    quinn = export("owners/quinn-harrow.json", "owner")
    by_year = {d["year"]: d for d in quinn["draft"]}
    assert by_year[2021]["grade"] == {"rank": 1, "of": 12, "total": 4}
    assert by_year[2022]["grade"] == {"rank": 1, "of": 12, "total": 0}
    picks = {p["overall"]: p for p in by_year[2021]["picks"]}
    assert (picks[36]["points"], picks[36]["valueOverSlot"]) == (500.0, 5)
    assert picks[12]["valueOverSlot"] == -1
    assert picks[36]["positionalFinish"] == 1  # the best K that Season

    tamsin = export("owners/tamsin-oake.json", "owner")
    assert {d["year"]: d["grade"] for d in tamsin["draft"]}[2021] == {"rank": 2, "of": 12, "total": 1}


def test_best_and_worst_picks_are_all_time_top_ten_with_ties_by_season_then_pick(export):
    doc = export("draft.json", "draft")
    best = doc["bestPicks"]
    assert len(best) == 10
    assert best[0] == {
        "year": 2021,
        "owner": owner("quinn"),
        "teamName": PEOPLE["quinn"][1],
        "overall": 36,
        "round": 3,
        "roundPick": 12,
        "player": {"name": "Fixture Player 036", "position": "K", "nflTeam": "CIN"},
        "positionalFinish": 1,
        "valueOverSlot": 5,
    }
    # Then pick 8 (+1), then the 0s from 2021 pick 1
    assert [(p["year"], p["overall"], p["valueOverSlot"]) for p in best[1:4]] == [
        (2021, 8, 1),
        (2021, 1, 0),
        (2021, 2, 0),
    ]
    worst = doc["worstPicks"]
    assert len(worst) == 10
    # The five -1 Ks, then the 0s from 2021 pick 1
    assert [(p["year"], p["overall"], p["valueOverSlot"]) for p in worst[:6]] == [
        (2021, 6, -1),
        (2021, 12, -1),
        (2021, 18, -1),
        (2021, 24, -1),
        (2021, 30, -1),
        (2021, 1, 0),
    ]


def test_best_drafters_average_each_owners_grade_rank(export):
    drafters = export("draft.json", "draft")["bestDrafters"]
    assert len(drafters) == 12
    assert drafters[0] == {"owner": owner("quinn"), "seasons": 2, "averageRank": 1.0}
    assert drafters[1] == {"owner": owner("tamsin"), "seasons": 2, "averageRank": 1.5}
    middle = drafters[2:9]
    assert {d["averageRank"] for d in middle} == {2.0}
    assert [d["owner"]["name"] for d in middle] == sorted(d["owner"]["name"] for d in middle)
    # Jory and Lyle (10th, 1st) -> 5.5; Marlo (12th, 1st) -> 6.5
    assert [(d["owner"]["slug"], d["averageRank"]) for d in drafters[9:]] == [
        (owner("jory")["slug"], 5.5),
        (owner("lyle")["slug"], 5.5),
        (owner("marlo")["slug"], 6.5),
    ]
    assert {d["owner"]["slug"] for d in drafters} == {owner(k)["slug"] for k in SEED_ORDER}
