"""Seam 1 for Fleeced and Most active (#66). All data is invented (ADR-0007).

Fixture rules (tests/espn_fixture.py): a trade swaps whoever holds the listed lineup slot; `lineup_points`
fixes what a Player scores each Week; every team has a lineup every Week, Weeks 1-17. Here the proposing
side's Player scores `10 + diff` a Week and the acceptor's scores 10, so the Margin is diff x Weeks.
"""

import json

from espn_fixture import NO_REPLACEMENT, FixtureMove, FixtureTrade, free_agent_id, lineup_player_id
from test_build import season as build_season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate


def season(year, **options):
    """A 2020-style Season whose Replacement points are 0 at every position, so Value added equals raw
    starter points unless a test sets pool_points_by_position itself."""
    options.setdefault("pool_points_by_position", NO_REPLACEMENT)
    return build_season(year, **options)


def transactions(archive, owners, tmp_path, pg_dsn) -> dict:
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "transactions.json").read_text(encoding="utf-8"))
    validate(doc, "transactions")
    return doc


def with_trades(year, trades):
    """A Season with trades (week, acceptor, proposer, slot, diff): the acceptor receives 10 + diff a Week."""
    s = season(year)
    s.trades, s.lineup_points = [], {}
    for week, a, b, slot, diff in trades:
        s.trades.append(FixtureTrade(week=week, a=a, b=b, slots=(slot,)))
        s.lineup_points[lineup_player_id(s.team_id(a), slot)] = 10.0
        s.lineup_points[lineup_player_id(s.team_id(b), slot)] = 10.0 + diff
    return s


def test_fleeced_is_exactly_the_five_largest_margins_ties_by_season_then_week(archive, owners, tmp_path, pg_dsn):
    with_trades(2020, [
        (9, "quinn", "pell", 1, 10),   # 90
        (9, "odie", "rue", 1, 8),      # 72
        (9, "tamsin", "lyle", 1, 6),   # 54
        (9, "marlo", "ines", 1, 4),    # 36
        (12, "abel", "wren", 1, 3),    # 18, Week 12
        (9, "cass", "jory", 1, 2),     # 18, Week 9: beats Week 12 for the last place
        (9, "quinn", "odie", 2, 0),    # a tie is never Fleeced
    ]).write(archive)  # fmt: skip
    with_trades(2021, [(9, "quinn", "pell", 1, 2)]).write(archive)  # 18 in a later Season: out

    trades = transactions(archive, owners, tmp_path, pg_dsn)["trades"]

    fleeced = sorted((t["margin"], t["year"], t["week"]) for t in trades if t["fleeced"])
    assert fleeced == [(18.0, 2020, 9), (36.0, 2020, 9), (54.0, 2020, 9), (72.0, 2020, 9), (90.0, 2020, 9)]
    assert len(trades) == 8


def test_most_active_counts_every_owners_trades_and_pickups(archive, owners, tmp_path, pg_dsn):
    s = with_trades(2020, [(3, "quinn", "pell", 1, 1), (5, "quinn", "odie", 2, 1)])
    s.moves = [
        FixtureMove(week=4, team="quinn", slot=3, add=free_agent_id(1), type="FREEAGENT"),
        FixtureMove(week=6, team="quinn", slot=4, add=free_agent_id(2)),
        FixtureMove(week=6, team="odie", slot=4, add=free_agent_id(3)),
        FixtureMove(week=7, team="pell", slot=4, add=free_agent_id(4), status="CANCELED", execution_type="CANCEL"),
        FixtureMove(week=8, team="rue", slot=3, type="ROSTER"),  # a drop is not a Pickup
    ]
    s.write(archive)

    activity = transactions(archive, owners, tmp_path, pg_dsn)["activity"]

    # Most moves first, then name; every Owner is listed
    assert activity[:4] == [
        {"owner": owner("quinn"), "trades": 2, "pickups": 2},
        {"owner": owner("odie"), "trades": 1, "pickups": 1},
        {"owner": owner("pell"), "trades": 1, "pickups": 0},
        {"owner": owner("abel"), "trades": 0, "pickups": 0},
    ]
    assert len(activity) == 12
