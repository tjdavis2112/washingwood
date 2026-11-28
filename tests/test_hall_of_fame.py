"""Seam 1 for the Hall of Fame (#73, #74): the three Induction bars -> hall-of-fame.json `inductees`.

All data is invented (ADR-0007). Fixture rules (tests/espn_fixture.py): every team has a lineup every Week,
byes included; lineup slot 1 is an RB starter and slot 9 an RB on the bench; `lineup_points` fixes what a
Player scores each Week he's in a lineup; `player_points` sets a Player's Season points. Drafted Players are
in no lineup unless a move or trade puts them there. An executed move puts its added Player in the team's
slot 1 (unless it names another) from its Week on.

Pool rules here (POOL): every pool RB but the ones named scores 100, so RB Replacement points are 100 and an
RB's Points above replacement is his Season points minus 100. Every other position's pool Players score 0,
so their Replacement points are 0: a WR's Points above replacement is his Season points, and a WR Pickup's
Value added is his raw starter points. A Season has 17 Weeks and 12 Picks per Round (3 Rounds), so a Pick
alone in his Round with Points above replacement X has a Round expectation of X / 12 and Points over
expected of 11X / 12, rounded. WR Picks are overall 2 and 8 (Round 1), 14 and 20 (Round 2).

The tests pin their own bars (BARS), so calibrating the real ones (ADR-0009) doesn't change them.
"""

import json

import pytest
from espn_fixture import (
    NO_REPLACEMENT,
    PEOPLE,
    FixtureMove,
    FixtureTrade,
    fixture_player_name,
    free_agent_id,
    lineup_player,
    lineup_player_id,
)
from test_build import season
from test_draft import owner

from washingwood import hall_of_fame as hof
from washingwood.build import build
from washingwood.contract import validate
from washingwood.hall_of_fame import main

BARS = {"PAR_BAR": 150.0, "POE_BAR": 110.0, "PICKUP_BAR": 80.0}
PAR_BAR, POE_BAR, PICKUP_BAR = BARS.values()

RB_REPLACEMENT = 100.0
POOL = {**NO_REPLACEMENT, 2: RB_REPLACEMENT}


@pytest.fixture(autouse=True)
def pinned_bars(monkeypatch):
    for name, value in BARS.items():
        monkeypatch.setattr(hof, name, value)


def pool_season(year, **options):
    return season(year, pool_points_by_position=POOL, **options)


def hall_of_fame(archive, owners, tmp_path, pg_dsn, out="export") -> dict:
    build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / out, dsn=pg_dsn)
    doc = json.loads((tmp_path / out / "hall-of-fame.json").read_text(encoding="utf-8"))
    validate(doc, "hallOfFame")
    return doc


def credited(doc) -> list[tuple[int, str, str]]:
    """(year, Player, credited Owner) of each Inductee, in document order."""
    return [(i["year"], i["name"], i["owner"]["name"]) for i in doc["inductees"]]


def lanes(inductee) -> list[tuple[str, float, str]]:
    return [(lane["lane"], lane["value"], lane["owner"]["name"]) for lane in inductee["lanes"]]


# -- Dominant --------------------------------------------------------------------------------------------


def test_a_player_season_at_the_bar_is_inducted_and_one_just_below_is_not(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    at_bar, below = lineup_player_id(s.team_id("quinn"), 1), lineup_player_id(s.team_id("pell"), 1)
    s.player_points = {at_bar: RB_REPLACEMENT + PAR_BAR, below: RB_REPLACEMENT + PAR_BAR - 0.01}
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert doc["inductees"] == [
        {
            "year": 2020,
            "scoringFormat": "PPR",
            "name": lineup_player(at_bar)[0],
            "position": "RB",
            "nflTeam": "BUF",  # proTeamId 2
            "owner": owner("quinn"),
            "teamName": PEOPLE["quinn"][1],
            "lanes": [{"lane": "dominant", "value": PAR_BAR, "owner": owner("quinn")}],
            "points": RB_REPLACEMENT + PAR_BAR,
            "positionalFinish": 1,
        }
    ]


def test_a_traded_player_is_credited_to_the_franchise_he_scored_most_starter_points_for(
    archive, owners, tmp_path, pg_dsn
):
    s = pool_season(2020)
    traded = lineup_player_id(s.team_id("odie"), 1)
    # Odie starts him Weeks 1-8 (8 starts), Rue Weeks 9-17 (9 starts)
    s.trades = [FixtureTrade(week=9, a="odie", b="rue")]
    s.lineup_points = {traded: 20.0}
    s.player_points = {traded: RB_REPLACEMENT + PAR_BAR + 50}
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert credited(doc) == [(2020, lineup_player(traded)[0], "Rue Calloway")]
    assert doc["inductees"][0]["teamName"] == PEOPLE["rue"][1]


def test_a_tie_on_starter_points_goes_to_the_earlier_acquisition(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    traded = lineup_player_id(s.team_id("rue"), 1)
    # Rue Weeks 1-8 and Odie Weeks 9-16 (8 starts each), then Marlo Week 17: Rue had him first, though
    # Odie's Franchise sorts first
    assert s.team_id("odie") < s.team_id("rue")
    s.trades = [FixtureTrade(week=9, a="rue", b="odie"), FixtureTrade(week=17, a="odie", b="marlo")]
    s.lineup_points = {traded: 20.0}
    s.player_points = {traded: RB_REPLACEMENT + PAR_BAR + 50}
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert credited(doc) == [(2020, lineup_player(traded)[0], "Rue Calloway")]


def test_a_player_who_never_started_is_not_eligible(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    benched = lineup_player_id(s.team_id("tamsin"), 9)  # on Tamsin's bench all Season
    s.player_points = {benched: RB_REPLACEMENT + PAR_BAR + 100}
    s.write(archive)

    assert hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"] == []


# -- Overachiever ----------------------------------------------------------------------------------------


def test_an_overachiever_at_the_bar_is_inducted_and_one_just_below_is_not(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    drafter, at_bar = s.pick(2)  # Round 1
    _, below = s.pick(14)  # Round 2
    # Alone in their Rounds: 120 - 120/12 = 110 over expected; 118.8 - 9.9 = 108.9, rounded to 109
    s.player_points = {at_bar: 120.0, below: 118.8}
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert doc["inductees"] == [
        {
            "year": 2020,
            "scoringFormat": "PPR",
            "name": fixture_player_name(at_bar),
            "position": "WR",
            "nflTeam": "BUF",  # proTeamId 2
            "owner": owner(drafter),
            "teamName": PEOPLE[drafter][1],
            "lanes": [{"lane": "overachiever", "value": POE_BAR, "owner": owner(drafter)}],
            "points": 120.0,
            "positionalFinish": 1,
        }
    ]


# -- Waiver legend ---------------------------------------------------------------------------------------


def test_a_waiver_legend_at_the_bar_is_inducted_and_one_just_below_is_not(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    at_bar, below = free_agent_id(1, position=3), free_agent_id(2, position=3)
    # Weeks 2-17: 16 starts each, at WR Replacement points 0
    s.moves = [FixtureMove(week=2, team="pell", add=at_bar), FixtureMove(week=2, team="quinn", add=below)]
    s.lineup_points = {at_bar: PICKUP_BAR / 16, below: 4.99}  # 80.0 and 79.84
    s.player_points = {at_bar: 80.0, below: 79.84}  # under PAR_BAR, so not Dominant
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert doc["inductees"] == [
        {
            "year": 2020,
            "scoringFormat": "PPR",
            "name": lineup_player(at_bar)[0],
            "position": "WR",
            "nflTeam": "GB",  # proTeamId 9
            "owner": owner("pell"),
            "teamName": PEOPLE["pell"][1],
            "lanes": [{"lane": "waiver_legend", "value": PICKUP_BAR, "owner": owner("pell")}],
            "points": 80.0,
            "positionalFinish": 1,
        }
    ]


def test_a_waiver_legend_with_no_season_points_is_inducted_with_null_points_and_finish(
    archive, owners, tmp_path, pg_dsn
):
    s = pool_season(2020)
    fa = free_agent_id(1, position=3)  # not in player_points: the Archive has no Season points for him
    s.moves = [FixtureMove(week=2, team="pell", add=fa)]
    s.lineup_points = {fa: 6.0}  # 96 over 16 starts
    s.write(archive)

    (inductee,) = hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"]
    assert (inductee["points"], inductee["positionalFinish"]) == (None, None)
    assert lanes(inductee) == [("waiver_legend", 96.0, "Pell Vantor")]


def test_the_best_of_several_pickups_counts_not_the_latest_or_their_sum(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    fa, other = free_agent_id(1, position=3), free_agent_id(2, position=3)
    s.moves = [
        FixtureMove(week=2, team="odie", add=fa),  # Weeks 2-11: 10 starts, 100
        FixtureMove(week=12, team="odie", add=other),  # drops him
        FixtureMove(week=13, team="marlo", add=fa),  # Weeks 13-17: 5 starts, 50
    ]
    s.lineup_points = {fa: 10.0, other: 0.0}
    s.player_points = {fa: 100.0}
    s.write(archive)

    (inductee,) = hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"]

    assert inductee["owner"] == owner("odie")
    assert lanes(inductee) == [("waiver_legend", 100.0, "Odie Brask")]


# -- Several lanes ---------------------------------------------------------------------------------------


def test_a_player_season_clearing_two_lanes_is_one_inductee_credited_to_the_dominant_owner(
    archive, owners, tmp_path, pg_dsn
):
    s = pool_season(2020)
    drafter, pid = s.pick(8)  # Round 1
    assert drafter != "rue"
    # Drafted, then picked up by Rue in Week 2, who starts him every Week for 0 points: Value added 0
    s.moves = [FixtureMove(week=2, team="rue", add=pid)]
    s.lineup_points = {pid: 0.0}
    s.player_points = {pid: 240.0}  # 240 above replacement; 240 - 20 = 220 over expected
    s.write(archive)

    (inductee,) = hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"]

    assert (inductee["name"], inductee["owner"], inductee["teamName"]) == (
        fixture_player_name(pid),
        owner("rue"),
        PEOPLE["rue"][1],
    )
    assert lanes(inductee) == [("dominant", 240.0, "Rue Calloway"), ("overachiever", 220, PEOPLE[drafter][0])]


def test_an_overachiever_who_is_also_a_waiver_legend_is_credited_to_the_drafting_owner(
    archive, owners, tmp_path, pg_dsn
):
    s = pool_season(2020)
    drafter, pid = s.pick(2)  # Round 1
    assert drafter != "rue"
    # Rue picks him up in Week 2: 16 starts at 6.0 is 96 Value added
    s.moves = [FixtureMove(week=2, team="rue", add=pid)]
    s.lineup_points = {pid: 6.0}
    s.player_points = {pid: 130.0}  # under PAR_BAR; 130 - 10.83 = 119 over expected
    s.write(archive)

    (inductee,) = hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"]

    assert (inductee["owner"], inductee["teamName"]) == (owner(drafter), PEOPLE[drafter][1])
    assert lanes(inductee) == [("overachiever", 119, PEOPLE[drafter][0]), ("waiver_legend", 96.0, "Rue Calloway")]


def test_a_dominant_waiver_legend_traded_away_is_credited_to_the_dominant_owner(archive, owners, tmp_path, pg_dsn):
    s = pool_season(2020)
    fa = free_agent_id(1, position=3)
    # Lyle picks him up in Week 2 and starts him Weeks 2-8 (7 starts, 84); Ines Weeks 9-17 (9 starts, 108)
    s.moves = [FixtureMove(week=2, team="lyle", add=fa)]
    s.trades = [FixtureTrade(week=9, a="lyle", b="ines")]
    s.lineup_points = {fa: 12.0}
    s.player_points = {fa: PAR_BAR + 10}
    s.write(archive)

    (inductee,) = hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"]

    assert (inductee["owner"], inductee["teamName"]) == (owner("ines"), PEOPLE["ines"][1])
    assert lanes(inductee) == [("dominant", PAR_BAR + 10, "Ines Dorrow"), ("waiver_legend", 84.0, "Lyle Fenwick")]


# -- No knock-out and order ------------------------------------------------------------------------------


def test_a_later_season_with_bigger_numbers_in_every_lane_leaves_earlier_inductees_unchanged(
    archive, owners, tmp_path, pg_dsn
):
    first = pool_season(2020)
    star = lineup_player_id(first.team_id("abel"), 1)
    _, overachiever = first.pick(2)
    _, filler = first.pick(8)
    waiver = free_agent_id(1, position=3)
    first.moves = [FixtureMove(week=2, team="pell", add=waiver)]
    first.lineup_points = {waiver: 5.5}  # 88 over 16 starts
    # Round 1 holds 180 Points above replacement (132 + 48): an expectation of 15, so 117 over expected
    first.player_points = {star: RB_REPLACEMENT + PAR_BAR + 5, overachiever: 132.0, filler: 48.0, waiver: 88.0}
    first.write(archive)
    before = hall_of_fame(archive, owners, tmp_path, pg_dsn, out="before")
    assert [lane["lane"] for i in before["inductees"] for lane in i["lanes"]] == [
        "dominant",
        "overachiever",
        "waiver_legend",
    ]

    later = pool_season(2021)
    bigger = lineup_player_id(later.team_id("cass"), 1)
    _, bigger_pick = later.pick(2)
    bigger_waiver = free_agent_id(2, position=3)
    later.moves = [FixtureMove(week=2, team="jory", add=bigger_waiver)]
    later.lineup_points = {bigger_waiver: 9.0}  # 144 over 16 starts
    # Round expectations held fixed (ADR-0009 drift): Round 1 again holds 180 in total, all on one Pick,
    # so the expectation stays 360 / 24 = 15 and this Pick is 165 over expected
    later.player_points = {bigger: RB_REPLACEMENT + PAR_BAR + 300, bigger_pick: 180.0, bigger_waiver: 144.0}
    later.write(archive)
    after = hall_of_fame(archive, owners, tmp_path, pg_dsn, out="after")

    assert [i["year"] for i in after["inductees"]] == [2021, 2021, 2021, 2020, 2020, 2020]
    assert [i for i in after["inductees"] if i["year"] == 2020] == before["inductees"]


def test_inductees_are_newest_season_first_then_highest_points_above_replacement(archive, owners, tmp_path, pg_dsn):
    s2020, s2021 = pool_season(2020), pool_season(2021)
    a, b = lineup_player_id(s2020.team_id("jory"), 1), lineup_player_id(s2020.team_id("wren"), 2)
    _, pick = s2020.pick(2)  # an Overachiever only (110 over expected): 120 above replacement sorts last
    s2020.player_points = {a: RB_REPLACEMENT + PAR_BAR + 1, b: RB_REPLACEMENT + PAR_BAR + 9, pick: 120.0}
    c = lineup_player_id(s2021.team_id("ines"), 1)
    s2021.player_points = {c: RB_REPLACEMENT + PAR_BAR}
    s2020.write(archive)
    s2021.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert credited(doc) == [
        (2021, lineup_player(c)[0], "Ines Dorrow"),
        (2020, lineup_player(b)[0], "Wren Solano"),
        (2020, lineup_player(a)[0], "Jory Paxton"),
        (2020, fixture_player_name(pick), PEOPLE[s2020.pick(2)[0]][0]),
    ]
    assert [i["positionalFinish"] for i in doc["inductees"]] == [1, 1, 2, 1]


# -- Calibration report ----------------------------------------------------------------------------------


def test_the_report_counts_every_lane_and_total_inductees_per_season_and_no_names(
    archive, owners, tmp_path, pg_dsn, capsys
):
    s = pool_season(2020)
    star = lineup_player_id(s.team_id("quinn"), 1)
    traded = lineup_player_id(s.team_id("odie"), 1)
    _, overachiever = s.pick(2)  # Round 1: 110 over expected
    _, both = s.pick(14)  # Round 2: picked up by Marlo, Dominant (240) and 220 over expected
    waiver = free_agent_id(1, position=3)
    s.trades = [FixtureTrade(week=9, a="odie", b="rue")]
    s.moves = [FixtureMove(week=2, team="marlo", slot=2, add=both), FixtureMove(week=2, team="pell", add=waiver)]
    s.lineup_points = {both: 0.0, waiver: 5.0}
    s.player_points = {
        star: RB_REPLACEMENT + PAR_BAR,
        traded: RB_REPLACEMENT + PAR_BAR + 80,
        overachiever: 120.0,
        both: 240.0,
        waiver: 80.0,
    }
    s.write(archive)

    code = main(["--report", "--archive", str(archive), "--owners", str(owners), "--pg", pg_dsn])

    out = capsys.readouterr().out
    assert code == 0
    names = [n for person in PEOPLE.values() for n in person[:2]]
    names += [fixture_player_name(s.pick(o)[1]) for o in range(1, 37)]
    names += [lineup_player(lineup_player_id(t, i))[0] for t in range(1, 13) for i in range(16)]
    names += [lineup_player(waiver)[0]]
    assert [n for n in names if n in out] == []
    # Each lane's table ends with the count at its current bar; the totals count a two-lane Player once
    sections = out.split("\n\n")
    rows = {
        title: next(line for line in sec.splitlines() if line.startswith("2020")).split()
        for title in ("Dominant", "Overachiever", "Waiver legend", "Inductees per Season")
        for sec in sections
        if sec.startswith(title)
    }
    assert rows["Dominant"][-1] == "3"
    assert rows["Overachiever"][-1] == "2"
    assert rows["Waiver legend"][-1] == "1"
    assert rows["Inductees per Season"] == ["2020", "3", "2", "1", "5"]

    # Trying other bars: only `traded` (PAR 230) and `both` (PAR 240, 220 over expected) clear
    argv = ["--report", "--archive", str(archive), "--owners", str(owners), "--pg", pg_dsn]
    assert main([*argv, "--par", "200", "--poe", "200", "--pickup", "81"]) == 0
    tried = capsys.readouterr().out
    assert "trying PAR_BAR 200, POE_BAR 200, PICKUP_BAR 81" in tried
    totals = next(sec for sec in tried.split("\n\n") if sec.startswith("Inductees per Season"))
    assert next(line for line in totals.splitlines() if line.startswith("2020")).split() == ["2020", "2", "1", "0", "2"]
    assert hof.PAR_BAR == PAR_BAR  # the constants are untouched
