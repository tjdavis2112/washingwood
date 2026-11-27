"""Seam 1 for weekly lineups and Box scores (#40). All data is invented.

The fixture writes one ESPN-shaped boxscore_wNN.json per Week (tests/espn_fixture.py). Each side's
lineup has 9 starters (QB, RB x2, WR x2, TE, FLEX, D/ST, K) whose points split the side's score for
that Week exactly, then 6 bench Players and one on IR (4.5 points each). Projections are points + 2.
"""

import json

import pytest
from espn_fixture import Season2018Style, team
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate
from washingwood.loader import LoadError

STARTER_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K"]


def export(archive, owners, tmp_path, pg_dsn, year):
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "box-scores" / f"{year}.json").read_text(encoding="utf-8"))
    validate(doc, "boxScores")
    return doc, out


def find(doc, period, key):
    slug = owner(key)["slug"]
    return next(
        m
        for m in doc["matchups"]
        if m["matchupPeriod"] == period and slug in (m["home"]["owner"]["slug"], m["away"]["owner"]["slug"])
    )


def test_every_played_matchup_gets_a_box_score_with_starters_bench_and_projections(archive, owners, tmp_path, pg_dsn):
    season(2021).write(archive)
    doc, _ = export(archive, owners, tmp_path, pg_dsn, 2021)
    assert doc["year"] == 2021
    # 2020-style Season: 103 Matchups, 2 of them byes
    assert len(doc["matchups"]) == 101
    m = doc["matchups"][0]
    assert (m["matchupPeriod"], m["weeks"], m["kind"]) == (1, [1], "regular")
    home = m["home"]
    (week,) = home["weeks"]
    assert week["week"] == 1
    assert [e["slot"] for e in week["starters"]] == STARTER_SLOTS
    assert [e["slot"] for e in week["bench"]] == ["BE"] * 6 + ["IR"]
    assert week["emptySlots"] == []
    assert round(sum(e["points"] for e in week["starters"]), 2) == home["score"] == 120.5
    first = week["starters"][0]
    assert (first["position"], first["projected"], first["nflTeam"]) == ("QB", round(first["points"] + 2, 2), "ATL")
    assert week["starters"][7]["position"] == "D/ST"
    assert home["projected"] == round(sum(e["projected"] for e in week["starters"]), 2)
    assert home["adjustment"] == 0
    assert m["winner"] == "home" and not m["isTie"]


def test_playoff_and_consolation_matchups_are_labelled(archive, owners, tmp_path, pg_dsn):
    season(2021).write(archive)
    doc, _ = export(archive, owners, tmp_path, pg_dsn, 2021)
    kinds = {(m["matchupPeriod"], m["kind"]) for m in doc["matchups"]}
    assert {(15, "playoff"), (15, "consolation"), (17, "thirdPlace")} <= kinds


def test_a_two_week_round_shows_each_weeks_lineup(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    doc, _ = export(archive, owners, tmp_path, pg_dsn, 2018)
    final = find(doc, 15, "quinn")
    assert final["weeks"] == [16, 17]
    side = final["home"] if final["home"]["owner"] == owner("quinn") else final["away"]
    assert [w["week"] for w in side["weeks"]] == [16, 17]
    week_totals = [round(sum(e["points"] for e in w["starters"]), 2) for w in side["weeks"]]
    assert week_totals == [60.25, 60.25]  # each Week's half of the combined 120.5
    assert side["score"] == 120.5


def test_a_player_who_did_not_play_has_no_points_and_a_box_score_only_player_is_loaded(
    archive, owners, tmp_path, pg_dsn
):
    season(2021, quirks=(3, "quinn")).write(archive)
    doc, _ = export(archive, owners, tmp_path, pg_dsn, 2021)
    m = find(doc, 3, "quinn")
    side = m["home"] if m["home"]["owner"] == owner("quinn") else m["away"]
    (week,) = side["weeks"]
    assert week["starters"][1]["points"] is None  # no actual stat row: didn't play
    assert week["starters"][1]["projected"] is not None
    assert any(e["name"].startswith("Lineup ") for e in week["bench"])


def test_starters_that_do_not_add_up_to_the_score_fail_the_build(archive, owners, tmp_path, pg_dsn):
    season(2021, bad_lineup=(3, "quinn")).write(archive)
    with pytest.raises(LoadError, match=r"Season 2021, Week 3: .*Harrow Hammers.*starters"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_a_manual_adjustment_shows_on_its_side(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], adjustments={"rue": 5.5}).write(archive)
    doc, _ = export(archive, owners, tmp_path, pg_dsn, 2018)
    m = find(doc, 4, "rue")
    side = m["home"] if m["home"]["owner"] == owner("rue") else m["away"]
    assert side["adjustment"] == 5.5


def test_a_season_without_box_scores_gets_no_box_score_document(archive, owners, tmp_path, pg_dsn):
    season(2021, box_scores=False).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    assert not (out / "box-scores" / "2021.json").exists()
    assert json.loads((out / "seasons" / "2021.json").read_text(encoding="utf-8"))["dataTier"] == "partial"
