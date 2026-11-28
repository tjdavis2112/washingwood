"""Seam 1 for Pickups (#63): waiver claims and free-agent adds -> transactions.json `pickups`.

All data is invented. Fixture rules (tests/espn_fixture.py): an executed move puts its added free agent
in the team's lineup slot (1 = an RB starter) from its Week on and drops whoever held the slot; every
team has a lineup every Week, byes included; `lineup_points` fixes what a Player scores each Week.
"""

import json

from espn_fixture import (
    NO_REPLACEMENT,
    PEOPLE,
    FixtureMove,
    FixtureTrade,
    Season2018Style,
    free_agent_id,
    lineup_player_id,
    team,
)
from test_build import SEED_ORDER
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


def pickup(n, key, year, week, via, points, weeks, scoring="PPR"):
    return {
        "name": f"Free Agent {n:03d}",
        "position": "RB",
        "nflTeam": "GB",
        "owner": owner(key),
        "teamName": PEOPLE[key][1],
        "year": year,
        "week": week,
        "via": via,
        "points": points,
        "value": points,  # Replacement points 0 here
        "weeksStarted": weeks,
        "scoringFormat": scoring,
    }


def test_2018_only_executed_claims_and_adds_load_and_the_item_names_the_team(archive, owners, tmp_path, pg_dsn):
    s = Season2018Style(2018, [team(k) for k in SEED_ORDER[2:12]], pool_points_by_position=NO_REPLACEMENT)
    s.moves = [
        # 2018: the row's teamId is often not the team the Player joined; the item's toTeamId is
        FixtureMove(week=3, team="odie", add=free_agent_id(1), row_team="rue"),
        FixtureMove(week=5, team="tamsin", slot=2, add=free_agent_id(2), type="FREEAGENT"),
        # 2018 cancelled claims are PENDING + CANCEL; failed claims carry a FAILED_* status
        FixtureMove(week=4, team="lyle", add=free_agent_id(3), status="PENDING", execution_type="CANCEL"),
        FixtureMove(week=6, team="marlo", add=free_agent_id(4), status="FAILED_MATCHUPACQUISITIONLIMIT"),
        # A 2018 standalone drop is a FREEAGENT row with only a DROP item: not a Pickup
        FixtureMove(week=7, team="ines", slot=3, type="FREEAGENT"),
    ]
    s.lineup_points = {free_agent_id(n): pts for n, pts in ((1, 8.0), (2, 5.0), (3, 50.0), (4, 50.0))}
    s.write(archive)

    doc = transactions(archive, owners, tmp_path, pg_dsn)

    # Weeks 3-17 and 5-17, playoff Weeks included
    assert doc["pickups"] == [
        pickup(1, "odie", 2018, 3, "waiver", 120.0, 15),
        pickup(2, "tamsin", 2018, 5, "free_agent", 65.0, 13),
    ]


def test_pending_cancelled_and_failed_claims_are_ignored(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    s.moves = [
        FixtureMove(week=2, team="abel", add=free_agent_id(1), type="FREEAGENT"),
        FixtureMove(week=3, team="cass", add=free_agent_id(2), status="PENDING", execution_type="EXECUTE"),
        FixtureMove(week=3, team="ines", add=free_agent_id(3), status="CANCELED", execution_type="CANCEL"),
        FixtureMove(week=3, team="jory", add=free_agent_id(4), status="FAILED_INVALIDPLAYERSOURCE"),
        FixtureMove(week=9, team="lyle", slot=3, type="ROSTER"),  # a standalone drop
    ]
    s.write(archive)

    pickups = transactions(archive, owners, tmp_path, pg_dsn)["pickups"]

    assert [(p["name"], p["owner"]["name"], p["via"]) for p in pickups] == [
        ("Free Agent 001", "Abel Trice", "free_agent")
    ]


def test_a_player_dropped_and_re_added_is_two_pickups_with_no_week_counted_twice(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    s.moves = [
        FixtureMove(week=4, team="quinn", add=free_agent_id(1), type="FREEAGENT"),
        FixtureMove(week=8, team="quinn", add=free_agent_id(2), type="FREEAGENT"),  # drops Free Agent 001
        FixtureMove(week=11, team="quinn", add=free_agent_id(1)),  # drops Free Agent 002, re-adds 001
    ]
    s.lineup_points = {free_agent_id(1): 7.0, free_agent_id(2): 3.0}
    s.write(archive)

    pickups = transactions(archive, owners, tmp_path, pg_dsn)["pickups"]

    assert pickups == [
        pickup(1, "quinn", 2020, 11, "waiver", 49.0, 7),
        pickup(1, "quinn", 2020, 4, "free_agent", 28.0, 4),
        pickup(2, "quinn", 2020, 8, "free_agent", 9.0, 3),
    ]


def test_a_drop_ends_a_traded_players_stint_and_another_teams_claim_explains_the_move(
    archive, owners, tmp_path, pg_dsn
):
    s = season(2020)
    traded = lineup_player_id(s.team_id("odie"), 1)
    s.trades = [FixtureTrade(week=3, a="odie", b="rue")]
    s.moves = [
        FixtureMove(week=6, team="rue", add=free_agent_id(5), type="FREEAGENT"),  # drops the traded Player
        FixtureMove(week=6, team="marlo", slot=4, add=traded),  # who joins Marlo the same Week
    ]
    s.lineup_points = {traded: 10.0, free_agent_id(5): 1.0}
    s.write(archive)

    doc = transactions(archive, owners, tmp_path, pg_dsn)

    (trade,) = doc["trades"]
    rue = next(x for x in trade["sides"] if x["owner"]["name"] == "Rue Calloway")
    assert (rue["total"], rue["players"][0]["weeksStarted"]) == (30.0, 3)  # Weeks 3-5
    assert [(p["owner"]["name"], p["week"], p["points"], p["weeksStarted"]) for p in doc["pickups"]] == [
        ("Marlo Quist", 6, 120.0, 12),
        ("Rue Calloway", 6, 12.0, 12),
    ]


def test_best_pickups_are_the_top_ten_with_ties_by_season_week_then_owner(archive, owners, tmp_path, pg_dsn):
    keys = SEED_ORDER[:11]
    s = season(2020)
    # Eleven adds in Week 2 (16 Weeks each): one point less per Owner down the list, except the last two tie
    s.moves = [FixtureMove(week=2, team=k, add=free_agent_id(i), type="FREEAGENT") for i, k in enumerate(keys)]
    s.lineup_points = {free_agent_id(i): 20.0 - i for i in range(len(keys))}
    s.lineup_points[free_agent_id(10)] = s.lineup_points[free_agent_id(9)]
    s.write(archive)

    pickups = transactions(archive, owners, tmp_path, pg_dsn)["pickups"]

    assert len(pickups) == 10
    assert [p["points"] for p in pickups] == [16 * (20.0 - i) for i in range(9)] + [176.0]
    # Wren Solano and Cass Imber tie on 176.0 (same Season and Week): the name decides, and Wren is cut
    assert pickups[-1]["owner"]["name"] == "Cass Imber"


def test_each_season_has_its_own_top_ten_pickups_newest_season_first(archive, owners, tmp_path, pg_dsn):
    keys = SEED_ORDER[:12]
    s2020 = season(2020)
    # Twelve adds in Week 3 (15 Weeks each), one point less per Owner down the list; Wren Solano (9th)
    # drops to 10.0, tying Cass Imber (10th) for the last place in the top 10
    s2020.moves = [FixtureMove(week=3, team=k, add=free_agent_id(i), type="FREEAGENT") for i, k in enumerate(keys)]
    s2020.lineup_points = {free_agent_id(i): 20.0 - i for i in range(len(keys))}
    s2020.lineup_points[free_agent_id(9)] = 10.0
    s2020.write(archive)
    s2021 = season(2021)
    s2021.moves = [FixtureMove(week=16, team="rue", add=free_agent_id(50))]
    s2021.lineup_points = {free_agent_id(50): 4.0}
    s2021.write(archive)

    doc = transactions(archive, owners, tmp_path, pg_dsn)

    assert [s["year"] for s in doc["seasonPickups"]] == [2021, 2020]
    assert doc["seasonPickups"][0]["pickups"] == [pickup(50, "rue", 2021, 16, "waiver", 8.0, 2)]
    top = doc["seasonPickups"][1]["pickups"]
    assert [p["points"] for p in top] == [15 * (20.0 - i) for i in range(9)] + [150.0]
    # Same Season, Week and points: the Owner name decides, so Cass Imber is in and Wren Solano is cut
    assert top[-1]["owner"]["name"] == "Cass Imber"


def test_pickups_rank_by_value_added_over_their_positions_replacement(archive, owners, tmp_path, pg_dsn):
    # Replacement points: QB 340 and WR 170 over 17 Weeks, so 20 and 10 a start
    s = season(2020, pool_points_by_position={**NO_REPLACEMENT, 1: 340.0, 3: 170.0})
    qb, wr = free_agent_id(1, position=1), free_agent_id(2, position=3)
    s.moves = [
        FixtureMove(week=2, team="abel", slot=0, add=qb, type="FREEAGENT"),
        FixtureMove(week=2, team="cass", slot=3, add=wr, type="FREEAGENT"),
    ]
    s.lineup_points = {qb: 22.0, wr: 15.0}
    s.write(archive)

    pickups = transactions(archive, owners, tmp_path, pg_dsn)["pickups"]

    # 16 starts each: the QB's 352 raw is worth 32; the WR's 240 raw is worth 80, so the WR ranks first
    assert [(p["position"], p["points"], p["value"]) for p in pickups] == [("WR", 240.0, 80.0), ("QB", 352.0, 32.0)]
