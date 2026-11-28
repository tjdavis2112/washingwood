"""Seam 1 for Transactions (#62): trades from mTransactions2 and weekly rosters -> transactions.json.

All data is invented. Fixture rules (tests/espn_fixture.py): every team has a lineup every Week, byes
included; a trade swaps whoever holds the listed lineup slots (1 = an RB starter, 10 = a bench WR);
`lineup_points` fixes what a Player scores each Week, and the K absorbs the difference.
"""

import json

import pytest
from espn_fixture import PEOPLE, FixtureTrade, Season2018Style, lineup_player_id, team
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate
from washingwood.loader import LoadError


def trades(archive, owners, tmp_path, pg_dsn) -> list[dict]:
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "transactions.json").read_text(encoding="utf-8"))
    validate(doc, "transactions")
    return doc["trades"]


def pid(s, key, slot):
    return lineup_player_id(s.team_id(key), slot)


def player(name, position, nfl_team, points, weeks):
    return {"name": name, "position": position, "nflTeam": nfl_team, "points": points, "weeksStarted": weeks}


def side(key, outcome, total, players):
    return {"owner": owner(key), "teamName": PEOPLE[key][1], "outcome": outcome, "total": total, "players": players}


def lineup_name(s, key, slot):
    return f"Lineup {s.team_id(key)}-{slot:02d}"


def test_a_2018_style_trade_takes_its_legs_from_trade_accept_and_counts_playoff_weeks(
    archive, owners, tmp_path, pg_dsn
):
    s = Season2018Style(2018, [team(k) for k in SEED_ORDER[2:12]])
    s.trades = [FixtureTrade(week=4, a="odie", b="rue", legs=True, team_actions=True)]
    s.lineup_points = {pid(s, "odie", 1): 10.0, pid(s, "rue", 1): 7.0}
    s.write(archive)

    (trade,) = trades(archive, owners, tmp_path, pg_dsn)

    # Weeks 4-17: ten regular-season Weeks plus four playoff Weeks
    assert trade == {
        "year": 2018,
        "week": 4,
        "scoringFormat": "PPR",
        "margin": 42.0,
        "fleeced": True,  # the Season's only trade, so one of the 5 largest Margins
        "sides": [
            side("rue", "won", 140.0, [player(lineup_name(s, "odie", 1), "RB", "BUF", 140.0, 14)]),
            side("odie", "lost", 98.0, [player(lineup_name(s, "rue", 1), "RB", "BUF", 98.0, 14)]),
        ],
    }


def test_a_2019_style_trade_is_rebuilt_from_roster_diffs_and_counts_starters_only(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    # Accepted in Week 6, on the rosters from Week 7: an RB starter and a bench WR each way
    s.trades = [FixtureTrade(week=6, a="odie", b="rue", slots=(1, 10), lag=1)]
    s.lineup_points = {pid(s, "odie", 1): 9.0, pid(s, "rue", 1): 9.0, pid(s, "odie", 10): 50.0, pid(s, "rue", 10): 30.0}
    s.write(archive)

    (trade,) = trades(archive, owners, tmp_path, pg_dsn)

    # Weeks 7-17 as starters; bench points never count, and equal sides are a tie (names order the sides)
    assert trade["week"] == 7
    assert trade["margin"] == 0.0
    assert trade["sides"] == [
        side("odie", "tied", 99.0, [player(lineup_name(s, "rue", 1), "RB", "BUF", 99.0, 11),
                                     player(lineup_name(s, "rue", 10), "WR", "IND", 0.0, 0)]),
        side("rue", "tied", 99.0, [player(lineup_name(s, "odie", 1), "RB", "BUF", 99.0, 11),
                                    player(lineup_name(s, "odie", 10), "WR", "IND", 0.0, 0)]),
    ]  # fmt: skip


def test_a_week_one_trade_is_diffed_against_the_draft_roster(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    s.trades = [FixtureTrade(week=1, a="tamsin", b="lyle", slots=(2,), draft_round=1)]
    tamsin_pick, lyle_pick = s.drafted("tamsin", 1), s.drafted("lyle", 1)
    s.lineup_points = {tamsin_pick: 6.0, lyle_pick: 5.0}
    s.write(archive)

    (trade,) = trades(archive, owners, tmp_path, pg_dsn)

    assert (trade["week"], trade["margin"]) == (1, 17.0)
    assert [(x["owner"]["name"], x["total"], x["players"][0]["weeksStarted"]) for x in trade["sides"]] == [
        ("Lyle Fenwick", 102.0, 17),
        ("Tamsin Oake", 85.0, 17),
    ]
    assert trade["sides"][0]["players"][0]["name"] == f"Fixture Player {tamsin_pick - 5000:03d}"


def test_a_commissioner_veto_kills_a_trade_and_a_minority_veto_does_not(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    s.trades = [
        FixtureTrade(week=8, a="marlo", b="ines", veto="commissioner"),
        FixtureTrade(week=9, a="abel", b="wren", veto="minority"),
        # The full legs on a second TRADE_ACCEPT, as for the cookie owner's own trades
        FixtureTrade(week=10, a="cass", b="jory", second_accept=True, team_actions=True),
    ]
    s.write(archive)

    got = trades(archive, owners, tmp_path, pg_dsn)

    # Newest first
    assert [(t["week"], sorted(x["owner"]["name"] for x in t["sides"])) for t in got] == [
        (10, ["Cass Imber", "Jory Paxton"]),
        (9, ["Abel Trice", "Wren Solano"]),
    ]


def test_a_stint_ends_when_the_player_is_traded_away(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    # The same two Players go back and forth: Weeks 3-5, then 6-9, then 10-17
    s.trades = [FixtureTrade(week=w, a="quinn", b="pell") for w in (3, 6, 10)]
    away, back = pid(s, "quinn", 1), pid(s, "pell", 1)
    s.lineup_points = {away: 10.0, back: 4.0}
    s.write(archive)

    got = trades(archive, owners, tmp_path, pg_dsn)

    scores = {t["week"]: {x["owner"]["name"]: (x["total"], x["players"][0]["weeksStarted"]) for x in t["sides"]}
              for t in got}  # fmt: skip
    assert scores == {
        10: {"Pell Vantor": (80.0, 8), "Quinn Harrow": (32.0, 8)},
        6: {"Quinn Harrow": (40.0, 4), "Pell Vantor": (16.0, 4)},
        3: {"Pell Vantor": (30.0, 3), "Quinn Harrow": (12.0, 3)},
    }


def test_a_season_with_no_trades_has_none(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)
    assert trades(archive, owners, tmp_path, pg_dsn) == []


def test_the_build_fails_on_a_player_who_moves_teams_without_a_trade(archive, owners, tmp_path, pg_dsn):
    s = season(2020, stray_move=(5, "odie", "rue", 3))
    s.write(archive)
    with pytest.raises(LoadError, match=r"Season 2020, Week 5: .*moved from .* to .* with no trade"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_the_build_fails_on_a_trade_no_roster_shows(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    s.trades = [FixtureTrade(week=5, a="odie", b="rue", moves=False)]
    s.write(archive)
    with pytest.raises(LoadError, match=r"Season 2020, Week 5: couldn't rebuild a trade"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_the_build_fails_when_the_trade_count_disagrees_with_espn(archive, owners, tmp_path, pg_dsn):
    s = season(2020, trade_counter_offset=1)
    s.trades = [FixtureTrade(week=5, a="odie", b="rue")]
    s.write(archive)
    with pytest.raises(LoadError, match=r"Season 2020: 1 trade\(s\) found, but ESPN's transactionCounter says 7"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)
