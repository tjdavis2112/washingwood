"""Seam 1: archive + owner mapping -> site data, end to end through a throwaway Postgres.

Drives washingwood.build.build() and checks only the JSON it writes. All data is invented.
"""

import json
import os
import subprocess
import sys

import pytest
from espn_fixture import PEOPLE, Season2018Style, Season2020Style, default_owners, team, write_owners

from washingwood.build import build
from washingwood.contract import validate
from washingwood.loader import LoadError
from washingwood.owners import OwnerMappingError, slugify

SEED_ORDER = ["quinn", "pell", "odie", "rue", "tamsin", "lyle", "marlo", "ines", "abel", "wren", "cass", "jory"]


def season(year, *, upsets=(), order=SEED_ORDER, overrides=None, **options):
    overrides = overrides or {}
    return Season2020Style(year, [overrides.get(k) or team(k) for k in order], upsets=set(upsets), **options)


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
    shelf = json.loads((tmp_path / "export" / "trophy-shelf.json").read_text(encoding="utf-8"))["owners"]
    lyle = [e for e in shelf if e["owner"]["name"] == "Lyle Fenwick"]
    assert len(lyle) == 1
    assert (lyle[0]["firstSeason"], lyle[0]["lastSeason"], lyle[0]["titles"]) == (2020, 2021, [2021])


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
    out = tmp_path / "export"

    def snapshot():
        return {f.relative_to(out).as_posix(): f.read_bytes() for f in sorted(out.rglob("*.json"))}

    run(archive, owners, tmp_path, pg_dsn)
    first = snapshot()
    run(archive, owners, tmp_path, pg_dsn)  # same database: every Season is reloaded in place

    owner_files = [f"owners/{slugify(PEOPLE[k][0])}.json" for k in SEED_ORDER]
    assert sorted(first) == sorted(
        [
            "draft.json",
            "league.json",
            "matchups.json",
            "owners.json",
            "seasons/2020.json",
            "seasons/2021.json",
            "trophy-shelf.json",
            *owner_files,
        ]
    )
    assert snapshot() == first


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


# --- Standings and Scoring format (#8) ---


def row(rank, slug, name, team_name, seed, *, regular_periods, points_for=None):
    """One expected standings row, using the fixture's rule: seed s goes (periods - s)-s,
    points for 1500 - s, points against 1400 + s."""
    return {
        "rank": rank,
        "owner": {"slug": slug, "name": name},
        "teamName": team_name,
        "record": {"wins": regular_periods - seed, "losses": seed, "ties": 0},
        "pointsFor": points_for if points_for is not None else 1500.0 - seed,
        "pointsAgainst": 1400.0 + seed,
        "playoffSeed": seed,
    }


def test_standings_list_every_franchise_in_final_order(archive, owners, tmp_path, pg_dsn):
    # Seed 5 wins the title; seeds 1-4 and 6 settle around it; 7-12 finish in seed order
    season(2020, upsets={"tamsin"}).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    r = lambda *a: row(*a, regular_periods=14)  # noqa: E731
    assert doc["standings"] == [
        r(1, "tamsin-oake", "Tamsin Oake", "Oake Oracles", 5),
        r(2, "pell-vantor", "Pell Vantor", "Vantor Vipers", 2),
        r(3, "quinn-harrow", "Quinn Harrow", "Harrow Hammers", 1),
        r(4, "odie-brask", "Odie Brask", "Brask Bruisers", 3),
        r(5, "rue-calloway", "Rue Calloway", "Calloway Comets", 4),
        r(6, "lyle-fenwick", "Lyle Fenwick", "Fenwick Foxes", 6),
        r(7, "marlo-quist", "Marlo Quist", "Quist Quakes", 7),
        r(8, "ines-dorrow", "Ines Dorrow", "Dorrow Drakes", 8),
        r(9, "abel-trice", "Abel Trice", "Trice Tritons", 9),
        r(10, "wren-solano", "Wren Solano", "Solano Sparks", 10),
        r(11, "cass-imber", "Cass Imber", "Imber Embers", 11),
        r(12, "jory-paxton", "Jory Paxton", "Paxton Pistons", 12),
    ]


def test_10_team_2018_style_season_loads_with_a_manual_adjustment_in_points_for(archive, owners, tmp_path, pg_dsn):
    # 10 teams, 4 playoff teams, two-week playoff periods; Odie has a +2.5 manual adjustment.
    # Points for must include it, as ESPN's does. (Matchup scores exclude it; #10 tests that.)
    teams = [team(k) for k in SEED_ORDER[:10]]
    Season2018Style(2018, teams, adjustments={"odie": 2.5}).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2018)

    validate(doc, "season")
    assert doc["teamCount"] == 10
    assert [p["owner"]["name"] for p in doc["podium"]] == ["Quinn Harrow", "Pell Vantor", "Odie Brask"]
    assert doc["lastPlace"]["owner"]["name"] == "Wren Solano"
    assert len(doc["standings"]) == 10
    odie = next(s for s in doc["standings"] if s["owner"]["slug"] == "odie-brask")
    assert odie["pointsFor"] == 1499.5  # 1500 - seed 3 + 2.5
    assert odie["record"] == {"wins": 10, "losses": 3, "ties": 0}


KEY_VALUES = [
    {"label": "Passing yard", "points": 0.04},
    {"label": "Passing TD", "points": 4.0},
    {"label": "Interception thrown", "points": -2.0},
    {"label": "Rushing yard", "points": 0.1},
    {"label": "Rushing TD", "points": 6.0},
    {"label": "Reception", "points": 1.0},
    {"label": "Receiving yard", "points": 0.1},
    {"label": "Receiving TD", "points": 6.0},
    {"label": "Fumble lost", "points": -2.0},
]
ROSTER_SLOTS = [
    {"slot": "QB", "count": 1},
    {"slot": "RB", "count": 2},
    {"slot": "WR", "count": 2},
    {"slot": "TE", "count": 1},
    {"slot": "FLEX", "count": 1},
    {"slot": "D/ST", "count": 1},
    {"slot": "K", "count": 1},
    {"slot": "BE", "count": 7},
]


def test_scoring_format_reads_ppr_plus_te_premium_from_per_position_overrides(archive, owners, tmp_path, pg_dsn):
    # Reception base 0; overrides give 1.0 to QB/RB/WR and 1.5 to TE
    season(2020, te_premium=True).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    assert doc["scoringFormat"] == {
        "label": "PPR + TE premium",
        "receptionPoints": 1.0,
        "tePremium": 0.5,
        "keyValues": KEY_VALUES,
        "rosterSlots": ROSTER_SLOTS,  # IR has a count of 0, so it's left out
    }


def test_scoring_format_without_overrides_is_plain_ppr(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    assert (doc["scoringFormat"]["label"], doc["scoringFormat"]["tePremium"]) == ("PPR", 0)


# --- Playoff bracket (#9) ---
# Fixture scores: the ESPN home side scores 120.5 when it wins and 99.75 when it loses;
# the away side scores 101.25 or 118.0. The bracket lists the better seed first.


def bside(seed, key, score):
    name, team_name, _ = PEOPLE[key]
    return {"seed": seed, "owner": {"slug": slugify(name), "name": name}, "teamName": team_name, "score": score}


def bgame(home, away, winner, *, bye=False):
    return {"home": home, "away": away, "winner": winner, "isTie": False, "isBye": bye}


def test_12_team_bracket_has_byes_rounds_in_order_and_the_third_place_game(archive, owners, tmp_path, pg_dsn):
    # Seed 5 (Tamsin) beats 4, then 1, then 2. Seed 1 (Quinn) wins the Third-place game over 3 (Odie).
    # Seeds 4 (Rue) and 6 (Lyle) play the 5th-place game in the same tier and period: it isn't in the bracket.
    season(2020, upsets={"tamsin"}).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    validate(doc, "season")
    assert doc["bracket"] == {
        "rounds": [
            {
                "name": "Quarterfinals",
                "matchupPeriod": 15,
                "weeks": [15],
                "matchups": [
                    bgame(bside(1, "quinn", None), None, None, bye=True),
                    bgame(bside(2, "pell", None), None, None, bye=True),
                    bgame(bside(3, "odie", 120.5), bside(6, "lyle", 101.25), "home"),
                    bgame(bside(4, "rue", 99.75), bside(5, "tamsin", 118.0), "away"),
                ],
            },
            {
                "name": "Semifinals",
                "matchupPeriod": 16,
                "weeks": [16],
                "matchups": [
                    bgame(bside(1, "quinn", 99.75), bside(5, "tamsin", 118.0), "away"),
                    bgame(bside(2, "pell", 120.5), bside(3, "odie", 101.25), "home"),
                ],
            },
            {
                "name": "Championship",
                "matchupPeriod": 17,
                "weeks": [17],
                "matchups": [bgame(bside(2, "pell", 99.75), bside(5, "tamsin", 118.0), "away")],
            },
        ],
        "thirdPlaceGame": {
            "matchupPeriod": 17,
            "weeks": [17],
            "matchup": bgame(bside(1, "quinn", 120.5), bside(3, "odie", 101.25), "home"),
        },
    }


def test_better_seed_is_listed_first_even_when_espn_calls_it_away(archive, owners, tmp_path, pg_dsn):
    s = season(2020)
    # Swap ESPN's home and away on the 3 v 6 quarterfinal (seed 3 wins)
    m = next(m for m in s.matchups()["schedule"] if m["matchupPeriodId"] == 15 and "away" in m)
    m["home"], m["away"] = m["away"], m["home"]
    m["winner"] = "AWAY"
    s.write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    qf = doc["bracket"]["rounds"][0]["matchups"]
    three_six = next(g for g in qf if not g["isBye"] and g["home"]["seed"] == 3)
    assert (three_six["away"]["seed"], three_six["winner"], three_six["home"]["score"]) == (6, "home", 120.5)


def test_2018_style_two_week_rounds_show_combined_scores(archive, owners, tmp_path, pg_dsn):
    # Periods 14 (Weeks 14-15) and 15 (Weeks 16-17). Each side's score is the two-week total
    # (the fixture splits it evenly across the two Weeks).
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2018)

    rounds = doc["bracket"]["rounds"]
    assert [(r["name"], r["matchupPeriod"], r["weeks"]) for r in rounds] == [
        ("Semifinals", 14, [14, 15]),
        ("Championship", 15, [16, 17]),
    ]
    assert rounds[0]["matchups"] == [
        bgame(bside(1, "quinn", 120.5), bside(4, "rue", 101.25), "home"),
        bgame(bside(2, "pell", 120.5), bside(3, "odie", 101.25), "home"),
    ]
    third = doc["bracket"]["thirdPlaceGame"]
    assert (third["matchupPeriod"], third["weeks"]) == (15, [16, 17])
    assert third["matchup"] == bgame(bside(3, "odie", 120.5), bside(4, "rue", 101.25), "home")


# --- Weekly results (#10) ---


def wside(key, score):
    name, team_name, _ = PEOPLE[key]
    return {"owner": {"slug": slugify(name), "name": name}, "teamName": team_name, "score": score}


def test_weekly_results_cover_every_matchup_period_in_order(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    validate(doc, "season")
    periods = doc["weeklyResults"]
    assert [(p["matchupPeriod"], p["weeks"]) for p in periods] == [(n, [n]) for n in range(1, 18)]
    # Every Franchise appears exactly once in every period: 6 regular-season Matchups, and in the
    # playoff periods byes, bracket, 5th-place and losers' ladder Matchups together
    assert [len(p["matchups"]) for p in periods] == [6] * 14 + [7, 6, 6]
    for p in periods:
        slugs = [s["owner"]["slug"] for m in p["matchups"] for s in (m["home"], m["away"]) if s]
        assert len(slugs) == len(set(slugs)) == 12, p["matchupPeriod"]


def test_weekly_results_flag_byes_and_ties(archive, owners, tmp_path, pg_dsn):
    # Period 3's first Matchup is a 110-110 tie; seeds 1 and 2 have byes in period 15
    season(2020, tie_period=3).write(archive)

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2020)

    by_period = {p["matchupPeriod"]: p["matchups"] for p in doc["weeklyResults"]}
    ties = [m for m in by_period[3] if m["isTie"]]
    assert len(ties) == 1
    assert (ties[0]["winner"], ties[0]["home"]["score"], ties[0]["away"]["score"]) == (None, 110.0, 110.0)
    assert not any(m["isTie"] for p, ms in by_period.items() if p != 3 for m in ms)

    byes = [m for m in by_period[15] if m["isBye"]]
    assert byes == [
        # The bye team's score that Week, as ESPN records it (the bracket shows no score: no game)
        {"home": wside("quinn", 110.25), "away": None, "winner": None, "isTie": False, "isBye": True},
        {"home": wside("pell", 110.25), "away": None, "winner": None, "isTie": False, "isBye": True},
    ]


def test_weekly_scores_exclude_manual_adjustments_and_two_week_periods_combine(archive, owners, tmp_path, pg_dsn):
    # Odie has a +2.5 manual adjustment on his period-4 Matchup. Points for includes it;
    # the Matchup score must not (it's shown as ESPN shows it).
    s = Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], adjustments={"odie": 2.5})
    s.write(archive)
    # Odie's raw score in that Matchup, straight from the ESPN-shaped fixture
    period4 = [m for m in s.matchups()["schedule"] if m["matchupPeriodId"] == 4]
    raw = next(m[side]["totalPoints"] for m in period4 for side in ("home", "away") if m[side]["adjustment"])

    doc = run_season(archive, owners, tmp_path, pg_dsn, 2018)

    exported4 = next(p for p in doc["weeklyResults"] if p["matchupPeriod"] == 4)["matchups"]
    odie = next(g[side] for g in exported4 for side in ("home", "away") if g[side]["owner"]["slug"] == "odie-brask")
    assert odie["score"] == raw  # 120.5 or 101.25, never with the 2.5 added
    assert [(p["matchupPeriod"], p["weeks"]) for p in doc["weeklyResults"]][-2:] == [(14, [14, 15]), (15, [16, 17])]
    final = next(g for g in doc["weeklyResults"][-1]["matchups"] if g["home"]["owner"]["slug"] == "quinn-harrow")
    assert final["home"]["score"] == 120.5  # the two-week total, not one Week's 60.25


def test_an_unplayed_matchup_fails_the_build(archive, owners, tmp_path, pg_dsn):
    # Only finished Seasons are loaded, so a played Matchup must have a result: HOME, AWAY or TIE.
    # (That's what lets "no winner" mean exactly "tie".)
    season(2020).write(archive)
    path = archive / "2020" / "league_mMatchupScore.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["schedule"][0]["winner"] = "UNDECIDED"
    path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(LoadError, match="Season 2020.*no result"):
        run_season(archive, owners, tmp_path, pg_dsn, 2020)


# --- Trophy shelf (#6) ---


def run_shelf(archive, owners, tmp_path, pg_dsn):
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    return json.loads((out / "trophy-shelf.json").read_text(encoding="utf-8"))


def test_trophy_shelf_counts_titles_and_runner_ups_and_marks_former_owners(archive, owners, tmp_path, pg_dsn):
    # 2019: no upsets, so seed 1 Quinn beats seed 2 Pell; Jory's team is "Paxton Pioneers".
    # 2020: seed 5 Tamsin beats Pell; Jory renames to "Paxton Pistons".
    # 2021: seed 6 Lyle (renamed "Fenwick Fog") beats Pell again. Nell replaces Jory, who leaves.
    season(2019, overrides={"jory": team("jory", name="Paxton Pioneers")}).write(archive)
    season(2020, upsets={"tamsin"}).write(archive)
    season(
        2021,
        upsets={"lyle"},
        overrides={"lyle": team("lyle", name="Fenwick Fog"), "jory": team("nell")},
    ).write(archive)

    shelf = run_shelf(archive, owners, tmp_path, pg_dsn)

    validate(shelf, "trophyShelf")
    entries = {e["owner"]["slug"]: e for e in shelf["owners"]}
    # Titles, then runner-ups (both descending), then name
    assert [e["owner"]["name"] for e in shelf["owners"]] == [
        "Lyle Fenwick", "Quinn Harrow", "Tamsin Oake",  # 1 title each
        "Pell Vantor",  # 3 runner-ups
        "Abel Trice", "Cass Imber", "Ines Dorrow", "Jory Paxton", "Marlo Quist",
        "Nell Ashgrove", "Odie Brask", "Rue Calloway", "Wren Solano",
    ]  # fmt: skip
    assert entries["lyle-fenwick"] == {
        "owner": {"slug": "lyle-fenwick", "name": "Lyle Fenwick"},
        "currentTeamName": "Fenwick Fog",  # the most recent Franchise's name
        "titles": [2021],
        "runnerUps": [],
        "firstSeason": 2019,
        "lastSeason": 2021,
        "isFormer": False,
    }
    assert entries["pell-vantor"]["runnerUps"] == [2019, 2020, 2021]
    assert entries["tamsin-oake"]["titles"] == [2020]
    # A former Owner keeps their history and their last team name (not the 2019 one)
    assert entries["jory-paxton"] | {"owner": None} == {
        "owner": None,
        "currentTeamName": "Paxton Pistons",
        "titles": [],
        "runnerUps": [],
        "firstSeason": 2019,
        "lastSeason": 2020,
        "isFormer": True,
    }
    assert (entries["nell-ashgrove"]["firstSeason"], entries["nell-ashgrove"]["isFormer"]) == (2021, False)


def test_a_franchise_mapped_to_two_owners_fails_the_build(archive, owners, tmp_path, pg_dsn):
    # One Owner per Franchise (GLOSSARY: Franchise). Nell's account is added to Tamsin's 2020 team
    s = season(2020, upsets={"tamsin"})
    s.write(archive)
    path = archive / "2020" / "league_mTeam.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    franchise = next(t for t in doc["teams"] if t["name"] == "Oake Oracles")
    franchise["owners"].append(PEOPLE["nell"][2])
    doc["members"].append({"id": PEOPLE["nell"][2], "displayName": "user13", "firstName": "X", "lastName": "Y"})
    path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(OwnerMappingError) as err:
        run(archive, owners, tmp_path, pg_dsn)

    assert "Season 2020" in str(err.value)
    assert "Oake Oracles" in str(err.value)
    assert "2 Owners" in str(err.value)
    assert not (tmp_path / "export" / "league.json").exists()


# --- Owner index (#13) ---


def test_owner_index_lists_every_owner_like_the_shelf_with_career_regular_season_records(
    archive, owners, tmp_path, pg_dsn
):
    # The trophy-shelf scenario: Lyle wins 2021 renamed; Nell replaces Jory, who leaves after 2020.
    # Fixture records come from the seed: seed s goes (14 - s)-s over 14 regular-season periods.
    season(2019, overrides={"jory": team("jory", name="Paxton Pioneers")}).write(archive)
    season(2020, upsets={"tamsin"}).write(archive)
    season(
        2021,
        upsets={"lyle"},
        overrides={"lyle": team("lyle", name="Fenwick Fog"), "jory": team("nell")},
    ).write(archive)
    out = tmp_path / "export"

    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)

    index = json.loads((out / "owners.json").read_text(encoding="utf-8"))
    shelf = json.loads((out / "trophy-shelf.json").read_text(encoding="utf-8"))
    validate(index, "ownerIndex")
    assert [e["owner"] for e in index["owners"]] == [e["owner"] for e in shelf["owners"]]
    entries = {e["owner"]["slug"]: e for e in index["owners"]}
    assert entries["lyle-fenwick"] == {
        "owner": {"slug": "lyle-fenwick", "name": "Lyle Fenwick"},
        "currentTeamName": "Fenwick Fog",
        "firstSeason": 2019,
        "lastSeason": 2021,
        "isFormer": False,
        "titles": [2021],
        "runnerUps": [],
        "regularSeason": {"wins": 24, "losses": 18, "ties": 0},  # seed 6 three times; playoff wins not counted
    }
    jory = entries["jory-paxton"]
    assert (jory["isFormer"], jory["regularSeason"]) == (True, {"wins": 4, "losses": 24, "ties": 0})
    assert entries["nell-ashgrove"]["regularSeason"] == {"wins": 2, "losses": 12, "ties": 0}


# --- Owner documents (#14) ---
# 2019 (2018-style, two-week rounds, no upsets): Quinn (1) beats Rue (4), Pell (2) beats Odie (3),
#   Quinn beats Pell for the title; Odie beats Rue in the Third-place game. Wren (10) is Last place.
# 2020 (seed 5 Tamsin upsets): byes for Quinn (1) and Pell (2). Quarterfinals: Odie (3) beats
#   Lyle (6), Tamsin (5) beats Rue (4). Semifinals: Tamsin beats Quinn, Pell beats Odie. Final:
#   Tamsin beats Pell. Third-place game: Quinn beats Odie. 5th-place game: Rue beats Lyle.
#   Jory (12) is Last place.


def owner_docs(archive, owners, tmp_path, pg_dsn):
    Season2018Style(2019, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    season(2020, upsets={"tamsin"}).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (out / "owners").glob("*.json")}


def test_every_owner_gets_a_valid_owner_document(archive, owners, tmp_path, pg_dsn):
    docs = owner_docs(archive, owners, tmp_path, pg_dsn)

    index = json.loads((tmp_path / "export" / "owners.json").read_text(encoding="utf-8"))
    assert sorted(docs) == sorted(e["owner"]["slug"] for e in index["owners"])
    for slug, doc in docs.items():
        validate(doc, "owner")
        assert doc["owner"]["slug"] == slug


def test_owner_header_trophies_and_career_summary(archive, owners, tmp_path, pg_dsn):
    quinn = owner_docs(archive, owners, tmp_path, pg_dsn)["quinn-harrow"]

    assert {k: quinn[k] for k in ("owner", "currentTeamName", "firstSeason", "lastSeason", "isFormer")} == {
        "owner": {"slug": "quinn-harrow", "name": "Quinn Harrow"},
        "currentTeamName": "Harrow Hammers",
        "firstSeason": 2019,
        "lastSeason": 2020,
        "isFormer": False,
    }
    assert quinn["trophies"] == {"titles": [2019], "runnerUps": [], "thirds": [2020]}
    assert quinn["career"] == {
        "regularSeason": {"wins": 25, "losses": 2, "ties": 0},  # seed 1 twice: 12-1 and 13-1
        # 2019: semifinal + final (two-week rounds, once each). 2020: the bye and the Third-place
        # game don't count, the semifinal loss does.
        "playoffs": {"wins": 2, "losses": 1, "ties": 0},
        "avgPointsFor": 111.04,  # (1499 + 1499) / 27
        "avgPointsAgainst": 103.78,  # (1401 + 1401) / 27
        "playoffAppearances": [2019, 2020],  # 2020 was a bye: it still counts
        "lastPlaces": [],
    }


def test_playoff_record_counts_only_winners_bracket_games_played(archive, owners, tmp_path, pg_dsn):
    docs = owner_docs(archive, owners, tmp_path, pg_dsn)
    playoffs = {slug: d["career"]["playoffs"] for slug, d in docs.items()}

    assert playoffs["tamsin-oake"] == {"wins": 3, "losses": 0, "ties": 0}  # quarterfinal, semifinal, final
    # Odie: 2019 semifinal loss (the Third-place win doesn't count); 2020 quarterfinal win, semifinal loss
    assert playoffs["odie-brask"] == {"wins": 1, "losses": 2, "ties": 0}
    # Rue: two losses; the 2020 5th-place win is a consolation game
    assert playoffs["rue-calloway"] == {"wins": 0, "losses": 2, "ties": 0}
    assert docs["rue-calloway"]["career"]["playoffAppearances"] == [2019, 2020]
    # Wren missed the playoffs and finished Last place in 2019
    wren = docs["wren-solano"]["career"]
    assert (wren["playoffs"], wren["playoffAppearances"], wren["lastPlaces"]) == (
        {"wins": 0, "losses": 0, "ties": 0},
        [],
        [2019],
    )
    assert docs["jory-paxton"]["career"]["lastPlaces"] == [2020]


def test_owner_seasons_are_newest_first_with_finish_markers(archive, owners, tmp_path, pg_dsn):
    docs = owner_docs(archive, owners, tmp_path, pg_dsn)

    assert docs["quinn-harrow"]["seasons"] == [
        {
            "year": 2020, "teamName": "Harrow Hammers", "record": {"wins": 13, "losses": 1, "ties": 0},
            "pointsFor": 1499.0, "pointsAgainst": 1401.0, "playoffSeed": 1, "finalRank": 3,
            "podiumPlace": 3, "isLastPlace": False,
        },
        {
            "year": 2019, "teamName": "Harrow Hammers", "record": {"wins": 12, "losses": 1, "ties": 0},
            "pointsFor": 1499.0, "pointsAgainst": 1401.0, "playoffSeed": 1, "finalRank": 1,
            "podiumPlace": 1, "isLastPlace": False,
        },
    ]  # fmt: skip
    assert [(s["year"], s["podiumPlace"], s["isLastPlace"]) for s in docs["wren-solano"]["seasons"]] == [
        (2020, None, False),
        (2019, None, True),
    ]


def test_head_to_head_splits_regular_season_and_playoffs_and_skips_the_third_place_game(
    archive, owners, tmp_path, pg_dsn
):
    docs = owner_docs(archive, owners, tmp_path, pg_dsn)

    def h2h(a, b):
        return next((h for h in docs[a]["headToHead"] if h["opponent"]["slug"] == b), None)

    assert h2h("quinn-harrow", "tamsin-oake")["playoffs"] == {"wins": 0, "losses": 1, "ties": 0}
    assert h2h("tamsin-oake", "quinn-harrow")["playoffs"] == {"wins": 1, "losses": 0, "ties": 0}
    # Quinn and Odie met only in the 2020 Third-place game in the playoffs: it doesn't count
    assert h2h("quinn-harrow", "odie-brask")["playoffs"] == {"wins": 0, "losses": 0, "ties": 0}
    for slug, doc in docs.items():
        for row in doc["headToHead"]:
            back = h2h(row["opponent"]["slug"], slug)
            assert row["meetings"] == back["meetings"] > 0
            assert row["regularSeason"]["wins"] == back["regularSeason"]["losses"]
        meetings = [row["meetings"] for row in doc["headToHead"]]
        assert meetings == sorted(meetings, reverse=True)


# --- Owner season rows (#15) ---


def test_owner_season_rows_keep_each_seasons_team_name(archive, owners, tmp_path, pg_dsn):
    season(2019, overrides={"jory": team("jory", name="Paxton Pioneers")}).write(archive)
    season(2020).write(archive)
    out = tmp_path / "export"

    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)

    jory = json.loads((out / "owners" / "jory-paxton.json").read_text(encoding="utf-8"))
    assert [(s["year"], s["teamName"]) for s in jory["seasons"]] == [
        (2020, "Paxton Pistons"),
        (2019, "Paxton Pioneers"),
    ]
    assert jory["currentTeamName"] == "Paxton Pistons"


def test_last_place_who_wins_a_consolation_game_is_still_flagged_last_place(archive, owners, tmp_path, pg_dsn):
    # Seed 12 Jory wins the last consolation game and finishes 11th, above seed 11 Cass
    season(2020, last_place_climbs=True).write(archive)
    out = tmp_path / "export"

    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)

    def row(slug):
        doc = json.loads((out / "owners" / f"{slug}.json").read_text(encoding="utf-8"))
        s = doc["seasons"][0]
        return s["playoffSeed"], s["finalRank"], s["isLastPlace"], doc["career"]["lastPlaces"]

    assert row("jory-paxton") == (12, 11, True, [2020])
    assert row("cass-imber") == (11, 12, False, [])


# --- Head-to-head (#16) ---


def test_head_to_head_includes_former_owners_and_leaves_out_owners_who_never_met(archive, owners, tmp_path, pg_dsn):
    # 2019 (10 teams) includes Wren; in 2020 Nell takes Wren's slot and Wren leaves.
    # Wren never played Nell, Cass or Jory (all 2020 only).
    Season2018Style(2019, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    season(2020, overrides={"wren": team("nell")}).write(archive)
    out = tmp_path / "export"

    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)

    def opponents(slug):
        doc = json.loads((out / "owners" / f"{slug}.json").read_text(encoding="utf-8"))
        return {h["opponent"]["slug"]: h for h in doc["headToHead"]}

    quinn, wren = opponents("quinn-harrow"), opponents("wren-solano")
    assert "wren-solano" in quinn  # a former Owner keeps their rows
    assert quinn["wren-solano"]["meetings"] == wren["quinn-harrow"]["meetings"] > 0
    assert not {"nell-ashgrove", "cass-imber", "jory-paxton"} & set(wren)
    assert "wren-solano" not in opponents("nell-ashgrove")
    assert "quinn-harrow" not in quinn  # never their own opponent
