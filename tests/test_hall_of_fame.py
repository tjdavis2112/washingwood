"""Seam 1 for the Hall of Fame tracer (#73): the Dominant lane -> hall-of-fame.json `inductees`.

All data is invented (ADR-0007). Fixture rules (tests/espn_fixture.py): every team has a lineup every Week,
byes included; lineup slot 1 is an RB starter and slot 9 an RB on the bench; `lineup_points` fixes what a
Player scores each Week he's in a lineup; `player_points` sets a lineup Player's Season points. Every pool
RB but the ones named scores 100, so RB Replacement points are 100 and Points above replacement is a named
RB's Season points minus 100.
"""

import json

from espn_fixture import PEOPLE, FixtureTrade, lineup_player, lineup_player_id
from test_build import season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate
from washingwood.hall_of_fame import PAR_BAR, main

RB_REPLACEMENT = 100.0
RB_POOL = {2: RB_REPLACEMENT}


def rb_season(year, **options):
    return season(year, pool_points_by_position=RB_POOL, **options)


def hall_of_fame(archive, owners, tmp_path, pg_dsn, out="export") -> dict:
    build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / out, dsn=pg_dsn)
    doc = json.loads((tmp_path / out / "hall-of-fame.json").read_text(encoding="utf-8"))
    validate(doc, "hallOfFame")
    return doc


def dominant(doc) -> list[tuple[int, str, str]]:
    """(year, Player, credited Owner) of each Inductee, in document order."""
    return [(i["year"], i["name"], i["owner"]["name"]) for i in doc["inductees"]]


def test_a_player_season_at_the_bar_is_inducted_and_one_just_below_is_not(archive, owners, tmp_path, pg_dsn):
    s = rb_season(2020)
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
    s = rb_season(2020)
    traded = lineup_player_id(s.team_id("odie"), 1)
    # Odie starts him Weeks 1-8 (8 starts), Rue Weeks 9-17 (9 starts)
    s.trades = [FixtureTrade(week=9, a="odie", b="rue")]
    s.lineup_points = {traded: 20.0}
    s.player_points = {traded: RB_REPLACEMENT + PAR_BAR + 50}
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert dominant(doc) == [(2020, lineup_player(traded)[0], "Rue Calloway")]
    assert doc["inductees"][0]["teamName"] == PEOPLE["rue"][1]


def test_a_tie_on_starter_points_goes_to_the_earlier_acquisition(archive, owners, tmp_path, pg_dsn):
    s = rb_season(2020)
    traded = lineup_player_id(s.team_id("rue"), 1)
    # Rue Weeks 1-8 and Odie Weeks 9-16 (8 starts each), then Marlo Week 17: Rue had him first, though
    # Odie's Franchise sorts first
    assert s.team_id("odie") < s.team_id("rue")
    s.trades = [FixtureTrade(week=9, a="rue", b="odie"), FixtureTrade(week=17, a="odie", b="marlo")]
    s.lineup_points = {traded: 20.0}
    s.player_points = {traded: RB_REPLACEMENT + PAR_BAR + 50}
    s.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert dominant(doc) == [(2020, lineup_player(traded)[0], "Rue Calloway")]


def test_a_player_who_never_started_is_not_eligible(archive, owners, tmp_path, pg_dsn):
    s = rb_season(2020)
    benched = lineup_player_id(s.team_id("tamsin"), 9)  # on Tamsin's bench all Season
    s.player_points = {benched: RB_REPLACEMENT + PAR_BAR + 100}
    s.write(archive)

    assert hall_of_fame(archive, owners, tmp_path, pg_dsn)["inductees"] == []


def test_a_later_season_with_a_bigger_dominant_season_leaves_earlier_inductees_unchanged(
    archive, owners, tmp_path, pg_dsn
):
    first = rb_season(2020)
    star = lineup_player_id(first.team_id("abel"), 1)
    first.player_points = {star: RB_REPLACEMENT + PAR_BAR + 5}
    first.write(archive)
    before = hall_of_fame(archive, owners, tmp_path, pg_dsn, out="before")

    later = rb_season(2021)
    bigger = lineup_player_id(later.team_id("cass"), 1)
    later.player_points = {bigger: RB_REPLACEMENT + PAR_BAR + 300}
    later.write(archive)
    after = hall_of_fame(archive, owners, tmp_path, pg_dsn, out="after")

    assert dominant(after) == [(2021, lineup_player(bigger)[0], "Cass Imber"), *dominant(before)]
    assert [i for i in after["inductees"] if i["year"] == 2020] == before["inductees"]


def test_inductees_are_newest_season_first_then_highest_points_above_replacement(archive, owners, tmp_path, pg_dsn):
    s2020, s2021 = rb_season(2020), rb_season(2021)
    a, b = lineup_player_id(s2020.team_id("jory"), 1), lineup_player_id(s2020.team_id("wren"), 2)
    s2020.player_points = {a: RB_REPLACEMENT + PAR_BAR + 1, b: RB_REPLACEMENT + PAR_BAR + 9}
    c = lineup_player_id(s2021.team_id("ines"), 1)
    s2021.player_points = {c: RB_REPLACEMENT + PAR_BAR}
    s2020.write(archive)
    s2021.write(archive)

    doc = hall_of_fame(archive, owners, tmp_path, pg_dsn)

    assert dominant(doc) == [
        (2021, lineup_player(c)[0], "Ines Dorrow"),
        (2020, lineup_player(b)[0], "Wren Solano"),
        (2020, lineup_player(a)[0], "Jory Paxton"),
    ]
    assert [i["positionalFinish"] for i in doc["inductees"]] == [1, 1, 2]


def test_the_report_prints_counts_per_season_and_no_player_or_owner_names(archive, owners, tmp_path, pg_dsn, capsys):
    s = rb_season(2020)
    star = lineup_player_id(s.team_id("quinn"), 1)
    traded = lineup_player_id(s.team_id("odie"), 1)
    s.trades = [FixtureTrade(week=9, a="odie", b="rue")]
    s.player_points = {star: RB_REPLACEMENT + PAR_BAR, traded: RB_REPLACEMENT + PAR_BAR + 80}
    s.write(archive)

    code = main(["--report", "--archive", str(archive), "--owners", str(owners), "--pg", pg_dsn])

    out = capsys.readouterr().out
    assert code == 0
    assert "2020" in out
    names = [n for person in PEOPLE.values() for n in person[:2]] + [lineup_player(star)[0], lineup_player(traded)[0]]
    names += [lineup_player(lineup_player_id(t, i))[0] for t in range(1, 13) for i in range(16)]
    assert [n for n in names if n in out] == []
    # Two Player seasons clear the current bar in 2020
    season_row = next(line for line in out.splitlines() if line.startswith("2020"))
    assert season_row.split()[-1] == "2"
