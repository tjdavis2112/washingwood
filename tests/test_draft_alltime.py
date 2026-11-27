"""Seam 1 for Draft grades on Owner pages and the all-time Draft tables (#29). All data is invented.

Two Seasons. 2021 is #28's graded scenario: pick 36 (Quinn's last) scores 500 and pick 2 ties pick 1,
so Value over slot is +35 for pick 36, 0 for pick 2 and -1 for every other Pick. Draft grades: Quinn
1st (+33), Cass 2nd (-2), the other ten tied 3rd (-3). 2022 uses default points: every Pick 0, every
Franchise tied 1st.
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
    season(2021, player_points={5036: 500.0, 5002: 397.0}).write(archive)
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
    assert by_year[2021]["grade"] == {"rank": 1, "of": 12, "total": 33}
    assert by_year[2022]["grade"] == {"rank": 1, "of": 12, "total": 0}
    picks = {p["overall"]: p for p in by_year[2021]["picks"]}
    assert (picks[36]["points"], picks[36]["valueOverSlot"]) == (500.0, 35)
    assert picks[12]["valueOverSlot"] == -1
    assert picks[36]["positionalFinish"] == 1  # the best K that Season

    cass = export("owners/cass-imber.json", "owner")
    assert {d["year"]: d["grade"] for d in cass["draft"]}[2021] == {"rank": 2, "of": 12, "total": -2}


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
        "valueOverSlot": 35,
    }
    # Then the Value-over-slot-0 Picks: 2021 pick 2, then 2022 from pick 1
    assert [(p["year"], p["overall"], p["valueOverSlot"]) for p in best[1:4]] == [
        (2021, 2, 0),
        (2022, 1, 0),
        (2022, 2, 0),
    ]
    worst = doc["worstPicks"]
    assert len(worst) == 10
    assert {p["valueOverSlot"] for p in worst} == {-1}
    assert [(p["year"], p["overall"]) for p in worst] == [(2021, k) for k in (1, 3, 4, 5, 6, 7, 8, 9, 10, 11)]


def test_best_drafters_average_each_owners_grade_rank(export):
    drafters = export("draft.json", "draft")["bestDrafters"]
    assert len(drafters) == 12
    assert drafters[0] == {"owner": owner("quinn"), "seasons": 2, "averageRank": 1.0}
    assert drafters[1] == {"owner": owner("cass"), "seasons": 2, "averageRank": 1.5}
    rest = drafters[2:]
    assert {d["averageRank"] for d in rest} == {2.0}
    assert [d["owner"]["name"] for d in rest] == sorted(d["owner"]["name"] for d in rest)
    assert {d["owner"]["slug"] for d in drafters} == {owner(k)["slug"] for k in SEED_ORDER}
