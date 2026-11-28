"""Seam 1 for the Owner page Transactions tab (#65): trade records, net points and each Owner's top 5
Pickups in transactions.json. All data is invented (ADR-0007).

Fixture rules (tests/espn_fixture.py): a trade swaps whoever holds lineup slot 1; `lineup_points` fixes
what a Player scores each Week; every team has a lineup every Week, Weeks 1-17.
"""

import json
from dataclasses import replace

from espn_fixture import FixtureMove, FixtureTrade, default_owners, free_agent_id, lineup_player_id, team, write_owners
from test_build import season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate

SECOND_ACCOUNT = "{00000000-0000-4000-8000-0000000000b9}"  # invented: Quinn Harrow's second ESPN account


def transactions(archive, owners, tmp_path, pg_dsn) -> dict:
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "transactions.json").read_text(encoding="utf-8"))
    validate(doc, "transactions")
    return doc


def record(key, trades, won, lost, tied, net):
    return {"owner": owner(key), "trades": trades, "won": won, "lost": lost, "tied": tied, "netPoints": net}


def test_trade_records_and_net_points_count_a_two_account_franchise_once(archive, tmp_path, pg_dsn):
    # Quinn's Franchise lists two ESPN accounts, both Quinn's: still one Owner, one side per trade
    quinn = replace(team("quinn"), extra_members=(SECOND_ACCOUNT,))
    s = season(2020, overrides={"quinn": quinn})
    away, back = lineup_player_id(s.team_id("quinn"), 1), lineup_player_id(s.team_id("pell"), 1)
    tied_a, tied_b = lineup_player_id(s.team_id("odie"), 1), lineup_player_id(s.team_id("rue"), 1)
    # The same two Players go back and forth: Weeks 3-5, 6-9 and 10-17. Odie and Rue tie.
    s.trades = [FixtureTrade(week=w, a="quinn", b="pell") for w in (3, 6, 10)]
    s.trades.append(FixtureTrade(week=4, a="odie", b="rue"))
    s.lineup_points = {away: 10.0, back: 4.0, tied_a: 9.0, tied_b: 9.0}
    s.write(archive)
    mapping = default_owners()
    mapping["Quinn Harrow"].append(SECOND_ACCOUNT)
    owners = write_owners(tmp_path / "owners.yaml", mapping)

    doc = transactions(archive, owners, tmp_path, pg_dsn)

    # Quinn: received 12 (lost to 30), 40 (won over 16), 32 (lost to 80): net -18 + 24 - 48 = -42
    # Ordered by net points (highest first), then name
    assert doc["tradeRecords"] == [
        record("pell", 3, 2, 1, 0, 42.0),
        record("odie", 1, 0, 0, 1, 0.0),
        record("rue", 1, 0, 0, 1, 0.0),
        record("quinn", 3, 1, 2, 0, -42.0),
    ]


def test_every_owner_gets_their_top_five_pickups_all_time(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    # Six adds for Abel in different slots from Week 2 (16 Weeks each): the lowest is cut
    s.moves = [FixtureMove(week=2, team="abel", slot=slot, add=free_agent_id(n), type="FREEAGENT")
               for n, slot in enumerate((1, 2, 3, 4, 5, 6))]  # fmt: skip
    s.lineup_points = {free_agent_id(n): 10.0 - n for n in range(6)}
    s.write(archive)

    doc = transactions(archive, owners, tmp_path, pg_dsn)

    by_owner = {e["owner"]["slug"]: e["pickups"] for e in doc["ownerPickups"]}
    assert [e["owner"]["name"] for e in doc["ownerPickups"]] == sorted(e["owner"]["name"] for e in doc["ownerPickups"])
    assert len(by_owner) == 12  # every Owner, with or without Pickups
    assert [p["points"] for p in by_owner["abel-trice"]] == [16 * (10.0 - n) for n in range(5)]
    assert by_owner["cass-imber"] == []
