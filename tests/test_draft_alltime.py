"""Seam 1 for Draft grades on Owner pages and the all-time Draft tables (#29). All data is invented.

Two Seasons. 2021 is test_draft_grades.py's scenario without the undrafted K: pick 36 (Quinn's last,
the 6th K taken) scores 500 and pick 8 (the 2nd WR) ties pick 2 (the 1st WR). Value over slot: +5 for
pick 36, -1 for the other five Ks (6, 12, 18, 24, 30), +1 for pick 8, 0 for everything else. 2022 uses
default points. Points over expected compares each Pick with its Round's mean across both Seasons
(tests/draft_examples.py is the reference).
"""

import json

import draft_examples
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


def drafts(export):
    return {year: export(f"seasons/{year}.json", "season")["draft"] for year in (2021, 2022)}


def test_round_expectation_is_shared_across_seasons(export):
    by_year = drafts(export)
    expectations = draft_examples.round_expectations(list(by_year.values()))
    for d in by_year.values():
        poe = draft_examples.points_over_expected(d, expectations)
        assert {p["overall"]: p["pointsOverExpected"] for p in d["picks"]} == poe
        assert d["grades"] == draft_examples.grades(d, poe)
    # The same Pick scores less over expected in 2022, where pick 36 is back to its default 292 points
    p36 = {year: next(p for p in d["picks"] if p["overall"] == 36) for year, d in by_year.items()}
    assert p36[2021]["pointsOverExpected"] > p36[2022]["pointsOverExpected"]


def test_owner_draft_seasons_carry_their_grade_and_pick_values(export):
    by_year = drafts(export)
    quinn = export("owners/quinn-harrow.json", "owner")
    for d in quinn["draft"]:
        grade = next(g for g in by_year[d["year"]]["grades"] if g["owner"] == owner("quinn"))
        assert d["grade"] == {"rank": grade["rank"], "of": 12, "total": grade["total"]}
        assert d["grade"]["total"] == sum(p["pointsOverExpected"] for p in d["picks"])
    picks = {p["overall"]: p for p in quinn["draft"][-1]["picks"]}  # newest first: 2021 is last
    assert (picks[36]["points"], picks[36]["valueOverSlot"]) == (500.0, 5)
    assert picks[36]["positionalFinish"] == 1  # the best K that Season


def test_steals_hits_and_busts_are_all_time_top_ten_with_ties_by_season_then_pick(export):
    doc = export("draft.json", "draft")
    every = [{"year": year, **p} for year, d in drafts(export).items() for p in d["picks"] if p["player"] is not None]
    for key, value, sign in (("steals", "valueOverSlot", -1), ("hits", "pointsOverExpected", -1),
                             ("busts", "pointsOverExpected", 1)):  # fmt: skip
        ranked = sorted(every, key=lambda p: (sign * p[value], sign * p["points"], p["year"], p["overall"]))[:10]
        assert [(p["year"], p["overall"]) for p in doc[key]] == [(p["year"], p["overall"]) for p in ranked], key
    # Steals: pick 36 (+5), then pick 8 (+1)
    assert doc["steals"][0] == {
        "year": 2021,
        "owner": owner("quinn"),
        "teamName": PEOPLE["quinn"][1],
        "overall": 36,
        "round": 3,
        "roundPick": 12,
        "player": {"name": "Fixture Player 036", "position": "K", "nflTeam": "CIN"},
        "points": 500.0,
        "positionalFinish": 1,
        "valueOverSlot": 5,
        "pointsOverExpected": doc["steals"][0]["pointsOverExpected"],
    }
    assert [(p["year"], p["overall"]) for p in doc["steals"][1:2]] == [(2021, 8)]
    # Hits: the WRs, far above the undrafted 50-point WR that sets their replacement level
    assert {p["player"]["position"] for p in doc["hits"][:4]} == {"WR"}


def test_best_drafters_average_each_owners_grade_rank(export):
    ranks = {}
    for d in drafts(export).values():
        for g in d["grades"]:
            ranks.setdefault(g["owner"]["slug"], []).append(g["rank"])
    drafters = export("draft.json", "draft")["bestDrafters"]
    assert len(drafters) == 12
    assert {d["owner"]["slug"]: d["averageRank"] for d in drafters} == {
        slug: round(sum(r) / len(r), 2) for slug, r in ranks.items()
    }
    assert all(d["seasons"] == 2 for d in drafters)
    assert [(d["averageRank"], d["owner"]["name"]) for d in drafters] == sorted(
        (d["averageRank"], d["owner"]["name"]) for d in drafters
    )
    assert {d["owner"]["slug"] for d in drafters} == {owner(k)["slug"] for k in SEED_ORDER}
