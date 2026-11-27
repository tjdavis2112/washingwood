"""Seam 1 for the Draft (#25): archive draft + players -> season.draft in the site data.

Drives washingwood.build.build() and checks only the JSON it writes. All data is invented.
"""

import json

import pytest
from espn_fixture import DRAFT_ROUNDS, PEOPLE, Season2018Style, Season2020Style, team
from test_build import SEED_ORDER, season

from washingwood.build import build
from washingwood.contract import validate
from washingwood.loader import LoadError
from washingwood.owners import slugify

SEED_ORDER_10 = SEED_ORDER[:10]


def owner(key):
    name = PEOPLE[key][0]
    return {"slug": slugify(name), "name": name}


def build_draft(archive, owners, tmp_path, pg_dsn, year):
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "seasons" / f"{year}.json").read_text(encoding="utf-8"))
    validate(doc, "season")
    return doc["draft"]


def test_snake_draft_lists_every_pick_in_order_with_owner_and_player(archive, owners, tmp_path, pg_dsn):
    season(2021).write(archive)
    draft = build_draft(archive, owners, tmp_path, pg_dsn, 2021)

    assert draft["type"] == "snake"
    assert draft["rounds"] == DRAFT_ROUNDS
    assert draft["note"] is None
    # Round-1 order is worst seed first in the fixture; each slot carries that Season's team name
    first_round = list(reversed(SEED_ORDER))
    assert draft["order"] == [
        {"slot": i + 1, "owner": owner(k), "teamName": PEOPLE[k][1]} for i, k in enumerate(first_round)
    ]
    picks = draft["picks"]
    assert [p["overall"] for p in picks] == list(range(1, 12 * DRAFT_ROUNDS + 1))
    assert picks[0] == {
        "overall": 1,
        "round": 1,
        "roundPick": 1,
        "owner": owner("jory"),
        "player": {"name": "Fixture Player 001", "position": "RB", "nflTeam": "ATL"},
        "points": 397.0,
        "positionalFinish": 1,
        "valueOverSlot": 0,
    }
    # Snake: round 2 starts with the last pick of round 1
    assert (picks[12]["round"], picks[12]["roundPick"], picks[12]["owner"]) == (2, 1, owner("quinn"))
    assert [p["player"]["position"] for p in picks[:6]] == ["RB", "WR", "QB", "TE", "D/ST", "K"]
    assert picks[4]["player"] == {"name": "Team5 D/ST", "position": "D/ST", "nflTeam": "CLE"}


def test_offline_draft_shows_unrecorded_picks_as_null_with_a_note(archive, owners, tmp_path, pg_dsn):
    teams = [team(k) for k in SEED_ORDER_10]
    Season2018Style(2018, teams, draft_type="OFFLINE", unrecorded_picks={28, 29, 30}).write(archive)
    draft = build_draft(archive, owners, tmp_path, pg_dsn, 2018)

    assert draft["type"] == "offline"
    assert [p["overall"] for p in draft["picks"] if p["player"] is None] == [28, 29, 30]
    assert draft["note"] == "Drafted offline and entered by hand. 3 picks weren't recorded."
    assert all(p["owner"] for p in draft["picks"])  # an unrecorded Pick still belongs to its Franchise


def test_a_player_drafted_in_two_seasons_carries_the_latest_seasons_name(archive, owners, tmp_path, pg_dsn):
    season(2021).write(archive)
    season(2022, player_names={5001: "Fixture Player Renamed"}).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    for year in (2021, 2022):
        doc = json.loads((out / "seasons" / f"{year}.json").read_text(encoding="utf-8"))
        assert doc["draft"]["picks"][0]["player"]["name"] == "Fixture Player Renamed"


def test_member_ids_on_picks_never_reach_the_site_data(archive, owners, tmp_path, pg_dsn):
    season(2021).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    for path in out.rglob("*.json"):
        assert "MEMBER-" not in path.read_text(encoding="utf-8"), path


def test_a_missing_pick_fails_the_build(archive, owners, tmp_path, pg_dsn):
    season(2021, missing_picks={7}).write(archive)
    with pytest.raises(LoadError, match=r"Season 2021: .*35 picks.*12 teams x 3 rounds"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_a_pick_whose_player_is_not_in_players_json_fails_the_build(archive, owners, tmp_path, pg_dsn):
    season(2021, unlisted_players={5002}).write(archive)
    with pytest.raises(LoadError, match=r"Season 2021: pick 2 .*not in players.json"):
        build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)


def test_rebuilding_a_season_replaces_its_picks(archive, owners, tmp_path, pg_dsn):
    season(2021).write(archive)
    build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "first", dsn=pg_dsn)
    draft = build_draft(archive, owners, tmp_path, pg_dsn, 2021)  # same database, loaded again
    assert len(draft["picks"]) == 12 * DRAFT_ROUNDS


def test_every_picks_owner_holds_exactly_one_draft_slot(archive, owners, tmp_path, pg_dsn):
    # The board places Picks in columns by Draft slot, so each Owner appears once in the order
    Season2020Style(2023, [team(k) for k in SEED_ORDER]).write(archive)
    draft = build_draft(archive, owners, tmp_path, pg_dsn, 2023)
    slugs = [o["owner"]["slug"] for o in draft["order"]]
    assert len(set(slugs)) == 12
    for p in draft["picks"]:
        assert p["owner"]["slug"] in slugs


# --- Owner -> Draft tab (#26) ---


def test_owner_document_lists_their_picks_per_season_newest_first(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2018, [team(k) for k in SEED_ORDER_10], draft_type="OFFLINE", unrecorded_picks={30}).write(archive)
    season(2021).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "owners" / "quinn-harrow.json").read_text(encoding="utf-8"))
    validate(doc, "owner")

    # Quinn is the top seed, so picks last in round 1: slot 10 of 10 in 2018, slot 12 of 12 in 2021
    assert [(d["year"], d["teamName"], d["slot"]) for d in doc["draft"]] == [
        (2021, "Harrow Hammers", 12),
        (2018, "Harrow Hammers", 10),
    ]
    assert [(p["overall"], p["round"], p["roundPick"]) for p in doc["draft"][0]["picks"]] == [
        (12, 1, 12),
        (13, 2, 1),
        (36, 3, 12),
    ]
    assert doc["draft"][0]["picks"][0]["player"] == {"name": "Fixture Player 012", "position": "K", "nflTeam": "KC"}
    # 2018: picks 10, 11, 30; the last one was never recorded
    assert [p["overall"] for p in doc["draft"][1]["picks"]] == [10, 11, 30]
    assert doc["draft"][1]["picks"][-1]["player"] is None
    assert "owner" not in doc["draft"][0]["picks"][0]  # it's this Owner's page: no Owner per Pick


# --- Draft section: first-round history (#27) ---


def test_draft_history_lists_each_seasons_first_round_newest_first(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2018, [team(k) for k in SEED_ORDER_10], draft_type="OFFLINE", unrecorded_picks={30}).write(archive)
    season(2021).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "draft.json").read_text(encoding="utf-8"))
    validate(doc, "draft")

    assert [(s["year"], s["teamCount"], s["type"]) for s in doc["seasons"]] == [
        (2021, 12, "snake"),
        (2018, 10, "offline"),
    ]
    first_2021 = doc["seasons"][0]["firstRound"]
    assert [p["overall"] for p in first_2021] == list(range(1, 13))
    # Worst seed picks first in the fixture
    assert first_2021[0] == {
        "overall": 1,
        "owner": owner("jory"),
        "teamName": PEOPLE["jory"][1],
        "player": {"name": "Fixture Player 001", "position": "RB", "nflTeam": "ATL"},
    }
    assert first_2021[-1]["owner"] == owner("quinn")
    assert len(doc["seasons"][1]["firstRound"]) == 10
