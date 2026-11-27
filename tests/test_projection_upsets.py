"""Seam 1 for the Projection upsets leaderboard (#41). All data is invented.

Fixture projections are points + 2 for each of the 9 starters, so a side's Projected score is its score
+ 18 and the winner is always the projected favourite, unless `projection_bonus` raises a side's
projection. Home wins regular-season games 120.5-101.25.

Scenario:
- 2021 Week 3 (first Matchup): the away loser's projection gets +50 -> projected 169.25 vs the winner's
  138.5: an upset by 30.75.
- 2021 Week 6 (first Matchup): +25 -> 144.25 vs 138.5: an upset by 5.75.
- A 2021 losers' consolation game (Week 15) gets +100 on its loser: not a Counted Matchup, not listed.
- 2018's two-week semifinal (Weeks 14-15) gets +100 on a loser: not counted either.
"""

import json

import pytest
from espn_fixture import PEOPLE, Season2018Style, team
from test_build import SEED_ORDER, season

from washingwood.build import build
from washingwood.contract import validate
from washingwood.owners import slugify


def loser_key(fixture, period, index):
    """Team key of the losing side of the period's index-th Matchup in the fixture's schedule."""
    keys = {v: k for k, v in fixture._ids.items()}
    m = [x for x in fixture._schedule if x["matchupPeriodId"] == period][index]
    side = m["away"] if m["winner"] == "HOME" else m["home"]
    return keys[side["teamId"]], m


def ref(key):
    return {"slug": slugify(PEOPLE[key][0]), "name": PEOPLE[key][0]}


@pytest.fixture
def upsets(archive, owners, tmp_path, pg_dsn):
    probe = season(2021)
    w3, m3 = loser_key(probe, 3, 0)
    w6, _ = loser_key(probe, 6, 0)
    cons, _ = loser_key(probe, 15, 4)
    s2018 = Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]])
    semi, _ = loser_key(s2018, 14, 0)
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], projection_bonus={(14, semi): 100.0}).write(archive)
    season(2021, projection_bonus={(3, w3): 50.0, (6, w6): 25.0, (15, cons): 100.0}).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "matchups.json").read_text(encoding="utf-8"))
    validate(doc, "matchups")
    keys = {v: k for k, v in probe._ids.items()}
    return doc["leaderboards"]["projectionUpsets"], keys[m3["home"]["teamId"]], w3


def test_projection_upsets_rank_by_how_far_behind_the_winner_was_projected(upsets):
    rows, winner, loser = upsets
    assert [(r["year"], r["matchupPeriod"], r["projectedDeficit"]) for r in rows] == [(2021, 3, 30.75), (2021, 6, 5.75)]
    top = rows[0]
    assert (top["winner"]["owner"], top["loser"]["owner"]) == (ref(winner), ref(loser))
    assert (top["winner"]["score"], top["loser"]["score"], top["margin"]) == (120.5, 101.25, 19.25)
    assert (top["winnerProjected"], top["loserProjected"]) == (138.5, 169.25)
    assert (top["kind"], top["weeks"], top["scoringFormat"]) == ("regular", [3], "PPR")


def test_consolation_games_and_two_week_rounds_are_not_listed(upsets):
    rows, _, _ = upsets
    assert all(r["year"] == 2021 and r["matchupPeriod"] < 14 for r in rows)
