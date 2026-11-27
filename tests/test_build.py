"""Seam 1: archive + owner mapping -> site data, end to end through a throwaway Postgres.

Drives washingwood.build.build() and checks only the JSON it writes. All data is invented.
"""

import json
import os
import subprocess
import sys

import pytest
from espn_fixture import Season2020Style, default_owners, team, write_owners

from washingwood.build import build
from washingwood.contract import validate
from washingwood.loader import LoadError
from washingwood.owners import OwnerMappingError

SEED_ORDER = ["quinn", "pell", "odie", "rue", "tamsin", "lyle", "marlo", "ines", "abel", "wren", "cass", "jory"]


def season(year, *, upsets=(), order=SEED_ORDER, overrides=None, **options):
    overrides = overrides or {}
    return Season2020Style(year, [overrides.get(k) or team(k) for k in order], upsets=set(upsets), **options)


@pytest.fixture
def archive(tmp_path):
    return tmp_path / "archive" / "999001"


@pytest.fixture
def owners(tmp_path):
    return write_owners(tmp_path / "owners.yaml", default_owners())


def run(archive, owners, tmp_path, pg_dsn):
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    return json.loads((out / "league.json").read_text(encoding="utf-8"))


def test_champion_is_the_winners_bracket_final_winner_not_the_top_seed(archive, owners, tmp_path, pg_dsn):
    # Seed 5 wins three playoff Matchups; the last period also holds two consolation-ladder games
    season(2020, upsets={"tamsin"}).write(archive)

    league = run(archive, owners, tmp_path, pg_dsn)

    validate(league, "league")
    assert league["champion"] == {
        "owner": {"slug": "tamsin-oake", "name": "Tamsin Oake"},
        "teamName": "Oake Oracles",
        "year": 2020,
    }
    assert league["seasons"] == [{"year": 2020, "teamCount": 12}]
    assert league["leagueName"] == "Example Fantasy League"


@pytest.mark.parametrize(
    ("years", "champion", "team_name"),
    [
        ([2020], "Tamsin Oake", "Oake Oracles"),
        ([2021], "Lyle Fenwick", "Fenwick Foxes"),
        ([2020, 2021], "Lyle Fenwick", "Fenwick Foxes"),
    ],
)
def test_current_champion_is_the_latest_seasons_champion(years, champion, team_name, archive, owners, tmp_path, pg_dsn):
    upsets = {2020: {"tamsin"}, 2021: {"lyle"}}  # seed 5 wins 2020, seed 6 wins 2021
    for y in years:
        season(y, upsets=upsets[y]).write(archive)

    league = run(archive, owners, tmp_path, pg_dsn)

    assert league["seasons"] == [{"year": y, "teamCount": 12} for y in years]
    assert (league["champion"]["owner"]["name"], league["champion"]["teamName"]) == (champion, team_name)
    assert league["champion"]["year"] == max(years)


SECOND_ACCOUNT = "{00000000-0000-4000-8000-0000000000a6}"  # invented


def test_owner_with_two_espn_accounts_comes_out_as_one_owner(archive, tmp_path, pg_dsn):
    # Lyle plays 2020 on one account, then wins 2021 on a second account under a new team name
    season(2020, upsets={"tamsin"}).write(archive)
    renamed = team("lyle", name="Fenwick Fog", member=SECOND_ACCOUNT)
    season(2021, upsets={"lyle"}, overrides={"lyle": renamed}).write(archive)
    mapping = default_owners()
    mapping["Lyle Fenwick"].append(SECOND_ACCOUNT)
    owners = write_owners(tmp_path / "owners.yaml", mapping)

    league = run(archive, owners, tmp_path, pg_dsn)

    assert league["champion"] == {
        "owner": {"slug": "lyle-fenwick", "name": "Lyle Fenwick"},
        "teamName": "Fenwick Fog",
        "year": 2021,
    }


def test_unmapped_team_fails_the_build_naming_the_season_and_team(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)
    stranger = team("jory", member="{00000000-0000-4000-8000-0000000000ff}")  # not in owners.yaml
    season(2021, overrides={"jory": stranger}).write(archive)

    with pytest.raises(OwnerMappingError) as err:
        run(archive, owners, tmp_path, pg_dsn)

    assert "Season 2021" in str(err.value)
    assert "Paxton Pistons" in str(err.value)
    assert not (tmp_path / "export" / "league.json").exists()


def test_rerunning_on_the_same_input_gives_byte_identical_output(archive, owners, tmp_path, pg_dsn):
    season(2020, upsets={"tamsin"}).write(archive)
    season(2021, upsets={"lyle"}).write(archive)
    out = tmp_path / "export" / "league.json"

    run(archive, owners, tmp_path, pg_dsn)
    first = out.read_bytes()
    run(archive, owners, tmp_path, pg_dsn)  # same database: every Season is reloaded in place

    assert out.read_bytes() == first


def test_build_command_writes_the_league_summary(archive, owners, tmp_path, pg_dsn):
    season(2020, upsets={"tamsin"}).write(archive)
    out = tmp_path / "cli-export"
    cmd = [
        sys.executable,
        "-m",
        "washingwood.build",
        "--archive",
        str(archive),
        "--owners",
        str(owners),
        "--out",
        str(out),
    ]

    done = subprocess.run(cmd, env={**os.environ, "WASHINGWOOD_PG": pg_dsn}, capture_output=True, text=True)

    assert done.returncode == 0, done.stderr
    validate(json.loads((out / "league.json").read_text(encoding="utf-8")), "league")
    assert pg_dsn not in done.stdout + done.stderr  # the DSN may hold a password; never print it


def test_build_command_reports_an_unmapped_team_and_exits_nonzero(archive, tmp_path, pg_dsn):
    season(2020).write(archive)
    owners = write_owners(tmp_path / "owners.yaml", {"Quinn Harrow": [team("quinn").member]})
    cmd = [
        sys.executable,
        "-m",
        "washingwood.build",
        "--archive",
        str(archive),
        "--owners",
        str(owners),
        "--pg",
        pg_dsn,
    ]

    done = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path)

    assert done.returncode == 1
    assert "Season 2020" in done.stderr and "not mapped" in done.stderr


def test_team_listing_two_accounts_of_the_same_owner_loads(archive, tmp_path, pg_dsn):
    # Both ESPN accounts sit on one 2021 team and both map to Lyle
    s = season(2021, upsets={"lyle"})
    lyle = next(t for t in s.teams()["teams"] if t["name"] == "Fenwick Foxes")
    lyle["owners"].append(SECOND_ACCOUNT)
    teams = s.teams()
    for t in teams["teams"]:
        if t["id"] == lyle["id"]:
            t["owners"] = lyle["owners"]
    s.write(archive)
    (archive / "2021" / "league_mTeam.json").write_text(json.dumps(teams), encoding="utf-8")
    mapping = default_owners()
    mapping["Lyle Fenwick"].append(SECOND_ACCOUNT)
    owners = write_owners(tmp_path / "owners.yaml", mapping)

    league = run(archive, owners, tmp_path, pg_dsn)

    assert league["champion"]["owner"] == {"slug": "lyle-fenwick", "name": "Lyle Fenwick"}


def run_season(archive, owners, tmp_path, pg_dsn, year):
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    return json.loads((out / "seasons" / f"{year}.json").read_text(encoding="utf-8"))


def spot(place, slug, name, team_name, wins, losses):
    return {
        "place": place,
        "owner": {"slug": slug, "name": name},
        "teamName": team_name,
        "record": {"wins": wins, "losses": losses, "ties": 0},
    }


def test_season_document_has_the_podium_even_when_a_5th_place_game_shares_the_tier(archive, owners, tmp_path, pg_dsn):
    # Seed 5 (Tamsin) wins it all, beating seed 2 (Pell); seed 1 (Quinn) wins the Third-place game.
    # The last period also holds a 5th-place game in the same tier, listed before the Third-place game.
    season(2020, upsets={"tamsin"}).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    validate(doc, "season")
    assert (doc["year"], doc["teamCount"]) == (2020, 12)
    assert doc["podium"] == [
        spot(1, "tamsin-oake", "Tamsin Oake", "Oake Oracles", 9, 5),
        spot(2, "pell-vantor", "Pell Vantor", "Vantor Vipers", 12, 2),
        spot(3, "quinn-harrow", "Quinn Harrow", "Harrow Hammers", 13, 1),
    ]


def test_last_place_is_the_highest_seed_even_after_it_climbs_in_final_rank(archive, owners, tmp_path, pg_dsn):
    # Seed 12 (Jory) wins its last consolation game and finishes 11th, above seed 11 (Cass)
    season(2020, last_place_climbs=True).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    assert doc["lastPlace"] == {
        "owner": {"slug": "jory-paxton", "name": "Jory Paxton"},
        "teamName": "Paxton Pistons",
        "record": {"wins": 2, "losses": 12, "ties": 0},
        "punishment": None,
    }


def test_a_season_where_espn_places_disagree_with_the_third_place_game_fails_loudly(archive, owners, tmp_path, pg_dsn):
    # Tamper with ESPN's final ranks so the Third-place game's winner isn't ranked 3rd
    season(2020).write(archive)
    path = archive / "2020" / "league_mTeam.json"
    teams = json.loads(path.read_text(encoding="utf-8"))
    by_rank = {t["rankCalculatedFinal"]: t for t in teams["teams"]}
    by_rank[3]["rankCalculatedFinal"], by_rank[4]["rankCalculatedFinal"] = 4, 3
    path.write_text(json.dumps(teams), encoding="utf-8")

    with pytest.raises(LoadError, match="Season 2020.*Third-place game"):
        run_season(archive, owners, tmp_path, pg_dsn, 2020)


def test_every_season_gets_its_own_document(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)
    season(2021).write(archive)
    build(archive_dir=archive, owners_file=owners, out_dir=tmp_path / "export", dsn=pg_dsn)
    assert sorted(p.name for p in (tmp_path / "export" / "seasons").iterdir()) == ["2020.json", "2021.json"]


def test_a_franchise_without_a_playoff_seed_fails_the_build(archive, owners, tmp_path, pg_dsn):
    # Seeds rank every Franchise 1..n; a missing one could make the wrong team Last place
    season(2020).write(archive)
    path = archive / "2020" / "league_mTeam.json"
    teams = json.loads(path.read_text(encoding="utf-8"))
    teams["teams"][0]["playoffSeed"] = None
    path.write_text(json.dumps(teams), encoding="utf-8")

    with pytest.raises(LoadError, match="Season 2020.*playoff seeds"):
        run_season(archive, owners, tmp_path, pg_dsn, 2020)
