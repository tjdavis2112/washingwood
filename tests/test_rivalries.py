"""Seam 1 for the rivalry grid and Rivalry pages (#39). All data is invented.

Scenario: 2020 (12 teams, seed 5 Tamsin upsets her way to the title) and 2021, where Nell takes Jory's
place, so Jory is a former Owner and Jory and Nell never met. In 2020 the semifinal losers Quinn and
Odie play the Third-place game, and Rue and Lyle (the quarterfinal losers) play two consolation games
(periods 16 and 17). Those three games are listed on the Rivalry pages but aren't in the records
(GLOSSARY: Rivalry, Playoff record).
"""

import json

import pytest
from espn_fixture import team
from test_build import season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate


@pytest.fixture
def out(archive, owners, tmp_path, pg_dsn):
    season(2020, upsets={"tamsin"}).write(archive)
    season(2021, overrides={"jory": team("nell")}).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    return out


def load(out, name, kind):
    doc = json.loads((out / name).read_text(encoding="utf-8"))
    validate(doc, kind)
    return doc


def pair(a, b):
    return "-vs-".join(sorted([owner(a)["slug"], owner(b)["slug"]]))


def test_a_rivalry_page_exists_for_every_pair_that_met_and_only_those(out):
    files = {p.stem for p in (out / "rivalries").glob("*.json")}
    assert pair("jory", "quinn") in files  # a former Owner's pairs exist
    assert pair("jory", "nell") not in files  # never met
    # 12 Owners in each Season, all meeting in the round robin: 66 pairs per Season; Jory's 11 and Nell's 11
    assert len(files) == 66 + 11


def test_rivalry_records_match_the_owner_pages_head_to_head(out):
    for path in (out / "rivalries").glob("*.json"):
        doc = load(out, f"rivalries/{path.name}", "rivalry")
        a, b = doc["sides"]
        assert a["owner"]["slug"] < b["owner"]["slug"]
        for me, them in ((a, b), (b, a)):
            h2h = load(out, f"owners/{me['owner']['slug']}.json", "owner")["headToHead"]
            row = next(r for r in h2h if r["opponent"] == them["owner"])
            assert (me["regularSeason"], me["playoffs"]) == (row["regularSeason"], row["playoffs"]), path.name
            assert doc["meetings"] == row["meetings"], path.name
        assert doc["meetings"] == sum(g["inRecord"] for g in doc["games"])


def test_third_place_and_consolation_games_are_listed_but_not_in_the_record(out):
    odie_quinn = load(out, f"rivalries/{pair('odie', 'quinn')}.json", "rivalry")
    third = [g for g in odie_quinn["games"] if g["kind"] == "thirdPlace"]
    assert [(g["year"], g["matchupPeriod"], g["inRecord"]) for g in third] == [(2020, 17, False)]

    lyle_rue = load(out, f"rivalries/{pair('lyle', 'rue')}.json", "rivalry")
    consolation = [
        (g["year"], g["matchupPeriod"], g["inRecord"]) for g in lyle_rue["games"] if g["kind"] == "consolation"
    ]
    assert consolation == [(2020, 17, False), (2020, 16, False)]  # newest first


def test_games_are_newest_first_and_biggest_wins_are_in_record_wins_by_the_largest_margin(out):
    doc = load(out, f"rivalries/{pair('pell', 'tamsin')}.json", "rivalry")
    keys = [(g["year"], g["matchupPeriod"]) for g in doc["games"]]
    assert keys == sorted(keys, reverse=True)
    for i, side in enumerate(doc["sides"]):
        wins = [g for g in doc["games"] if g["inRecord"] and g["winner"] == i]
        if not wins:
            assert side["biggestWin"] is None
            continue
        best = side["biggestWin"]
        assert best in wins
        assert best["margin"] == max(g["margin"] for g in wins)
    # The 2020 final: Tamsin (away, seed 5) beat Pell 118.0-99.75
    final = next(g for g in doc["games"] if (g["year"], g["matchupPeriod"]) == (2020, 17))
    tamsin = [s["owner"]["slug"] for s in doc["sides"]].index(owner("tamsin")["slug"])
    assert (final["kind"], final["inRecord"], final["winner"], final["teams"][tamsin]["score"]) == (
        "playoff",
        True,
        tamsin,
        118.0,
    )


def test_the_rivalry_grid_lists_owners_in_index_order_with_both_directions_of_every_pair(out):
    grid = load(out, "matchups.json", "matchups")["rivalryGrid"]
    index = [e["owner"] for e in load(out, "owners.json", "ownerIndex")["owners"]]
    assert grid["owners"] == index
    records = {(r["owner"], r["opponent"]): r for r in grid["records"]}
    assert len(records) == 2 * (66 + 11)
    assert (owner("jory")["slug"], owner("nell")["slug"]) not in records
    # Both directions agree, and match the Rivalry page (regular season plus playoffs)
    q, t = owner("quinn")["slug"], owner("tamsin")["slug"]
    qt, tq = records[(q, t)], records[(t, q)]
    assert (qt["wins"], qt["losses"], qt["ties"]) == (tq["losses"], tq["wins"], tq["ties"])
    doc = load(out, f"rivalries/{pair('quinn', 'tamsin')}.json", "rivalry")
    side = next(s for s in doc["sides"] if s["owner"]["slug"] == q)
    assert qt["wins"] == side["regularSeason"]["wins"] + side["playoffs"]["wins"]
    assert qt["losses"] == side["regularSeason"]["losses"] + side["playoffs"]["losses"]
