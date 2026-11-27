"""Tests for the site-data contract (washingwood.contract + contract/).

All Owners and team names here are invented (ADR-0007).
"""

import copy
import json

import pytest

from washingwood import contract as site_contract

ContractError = site_contract.ContractError
validate = site_contract.validate


def owner(slug, name):
    return {"slug": slug, "name": name}


LEAGUE = {
    "leagueName": "Test League",
    "seasons": [{"year": 2018, "teamCount": 10}],
    "champion": {"owner": owner("quinn-harrow", "Quinn Harrow"), "teamName": "Harrow Hammers", "year": 2018},
}


def _undocumented(node, path="#"):
    """Yield the path of every field and $def that has no description.

    A field is a property of a schema that declares `"type": "object"`. Refinements
    (if/then, allOf) reuse `properties` to add constraints, not to declare fields.
    """
    if isinstance(node, dict):
        for name, sub in node.get("$defs", {}).items():
            if "description" not in sub:
                yield f"{path}/$defs/{name}"
        if node.get("type") == "object":
            for name, sub in node.get("properties", {}).items():
                if "description" not in sub:
                    yield f"{path}/properties/{name}"
        for key, sub in node.items():
            yield from _undocumented(sub, f"{path}/{key}")
    elif isinstance(node, list):
        for i, sub in enumerate(node):
            yield from _undocumented(sub, f"{path}/{i}")


def test_every_schema_field_is_documented():
    assert list(_undocumented(site_contract.load_schema())) == []


def test_undocumented_check_catches_a_missing_description():
    schema = {"type": "object", "properties": {"documented": {"description": "x"}, "bare": {"type": "string"}}}
    assert list(_undocumented(schema)) == ["#/properties/bare"]


def test_valid_league_summary_passes():
    validate(LEAGUE, "league")


def test_league_summary_without_champion_is_rejected():
    doc = copy.deepcopy(LEAGUE)
    del doc["champion"]
    with pytest.raises(ContractError, match="champion"):
        validate(doc, "league")


SHELF = {
    "owners": [
        {
            "owner": owner("quinn-harrow", "Quinn Harrow"),
            "currentTeamName": "Harrow Hammers",
            "titles": [2018],
            "runnerUps": [],
            "firstSeason": 2018,
            "lastSeason": 2020,
            "isFormer": False,
        },
        {
            "owner": owner("pell-vantor", "Pell Vantor"),
            "currentTeamName": "Vantor Vipers",
            "titles": [],
            "runnerUps": [2018],
            "firstSeason": 2018,
            "lastSeason": 2018,
            "isFormer": True,
        },
    ]
}


def test_valid_trophy_shelf_passes():
    validate(SHELF, "trophyShelf")


def test_trophy_shelf_entry_without_former_flag_is_rejected():
    doc = copy.deepcopy(SHELF)
    del doc["owners"][1]["isFormer"]
    with pytest.raises(ContractError, match="isFormer"):
        validate(doc, "trophyShelf")


def test_trophy_shelf_rejects_a_title_year_listed_twice():
    doc = copy.deepcopy(SHELF)
    doc["owners"][0]["titles"] = [2018, 2018]
    with pytest.raises(ContractError, match="/owners/0/titles"):
        validate(doc, "trophyShelf")


A, B, C, D = (
    owner("quinn-harrow", "Quinn Harrow"),
    owner("pell-vantor", "Pell Vantor"),
    owner("odie-brask", "Odie Brask"),
    owner("rue-calloway", "Rue Calloway"),
)
TEAM = {
    A["slug"]: "Harrow Hammers",
    B["slug"]: "Vantor Vipers",
    C["slug"]: "Brask Bruisers",
    D["slug"]: "Calloway Comets",
}


def rec(w, losses, t=0):
    return {"wins": w, "losses": losses, "ties": t}


def side(o, score, seed=None):
    s = {"owner": o, "teamName": TEAM[o["slug"]], "score": score}
    if seed is not None:
        s["seed"] = seed
    return s


def matchup(home, away, winner, *, is_tie=False, is_bye=False):
    return {"home": home, "away": away, "winner": winner, "isTie": is_tie, "isBye": is_bye}


def season():
    """A tiny 4-team Season: one regular-season Week, a two-Week semifinal, then the final."""
    return {
        "year": 2018,
        "teamCount": 4,
        "dataTier": "full",
        "scoringFormat": {
            "label": "PPR",
            "receptionPoints": 1,
            "tePremium": 0,
            "keyValues": [{"label": "Passing TD", "points": 4}],
            "rosterSlots": [{"slot": "QB", "count": 1}, {"slot": "BE", "count": 7}],
        },
        "podium": [
            {"place": 1, "owner": A, "teamName": TEAM[A["slug"]], "record": rec(1, 0)},
            {"place": 2, "owner": B, "teamName": TEAM[B["slug"]], "record": rec(1, 0)},
            {"place": 3, "owner": C, "teamName": TEAM[C["slug"]], "record": rec(0, 1)},
        ],
        "lastPlace": {"owner": D, "teamName": TEAM[D["slug"]], "record": rec(0, 1), "punishment": None},
        "standings": [
            {
                "rank": i + 1,
                "owner": o,
                "teamName": TEAM[o["slug"]],
                "record": r,
                "pointsFor": 100.5,
                "pointsAgainst": 90.0,
                "playoffSeed": seed,
            }
            for i, (o, r, seed) in enumerate(
                [(A, rec(1, 0), 1), (B, rec(1, 0), 2), (C, rec(0, 1), 3), (D, rec(0, 1), 4)]
            )
        ],
        "bracket": {
            "rounds": [
                {
                    "name": "Semifinals",
                    "matchupPeriod": 2,
                    "weeks": [2, 3],
                    "matchups": [
                        matchup(side(A, 210.0, 1), side(D, 190.0, 4), "home"),
                        matchup(side(B, 205.0, 2), side(C, 200.0, 3), "home"),
                    ],
                },
                {
                    "name": "Championship",
                    "matchupPeriod": 3,
                    "weeks": [4, 5],
                    "matchups": [matchup(side(A, 220.0, 1), side(B, 215.0, 2), "home")],
                },
            ],
            "thirdPlaceGame": {
                "matchupPeriod": 3,
                "weeks": [4, 5],
                "matchup": matchup(side(C, 199.0, 3), side(D, 180.0, 4), "home"),
            },
        },
        "weeklyResults": [
            {
                "matchupPeriod": 1,
                "weeks": [1],
                "matchups": [
                    matchup(side(A, 100.5), side(C, 90.0), "home"),
                    matchup(side(B, 95.0), side(D, 95.0), None, is_tie=True),
                ],
            }
        ],
    }


def test_valid_season_passes():
    validate(season(), "season")


def test_podium_needs_exactly_three_places_in_order():
    short = season()
    short["podium"].pop()
    swapped = season()
    swapped["podium"][0], swapped["podium"][1] = swapped["podium"][1], swapped["podium"][0]
    for doc in (short, swapped):
        with pytest.raises(ContractError, match="/podium"):
            validate(doc, "season")


def test_last_place_must_carry_a_punishment_key():
    doc = season()
    del doc["lastPlace"]["punishment"]
    with pytest.raises(ContractError, match="punishment"):
        validate(doc, "season")


def test_last_place_punishment_can_hold_title_description_and_image():
    doc = season()
    doc["lastPlace"]["punishment"] = {"title": "Karaoke night", "description": "Sang three songs.", "image": None}
    validate(doc, "season")


def test_data_tier_must_be_full_or_partial():
    doc = season()
    doc["dataTier"] = "some"
    with pytest.raises(ContractError, match="dataTier"):
        validate(doc, "season")


def test_bye_has_no_away_side_and_no_winner():
    doc = season()
    doc["bracket"]["rounds"][0]["matchups"].append(matchup(side(A, None, 1), None, None, is_bye=True))
    validate(doc, "season")

    doc["bracket"]["rounds"][0]["matchups"][-1]["away"] = side(B, None, 2)
    with pytest.raises(ContractError, match="/bracket/rounds/0/matchups/2"):
        validate(doc, "season")


def test_decided_matchup_needs_a_winner_and_both_scores():
    no_winner = season()
    no_winner["weeklyResults"][0]["matchups"][0]["winner"] = None
    no_score = season()
    no_score["weeklyResults"][0]["matchups"][0]["away"]["score"] = None
    for doc in (no_winner, no_score):
        with pytest.raises(ContractError, match="/weeklyResults/0/matchups/0"):
            validate(doc, "season")


def test_third_place_game_is_never_a_bye():
    doc = season()
    doc["bracket"]["thirdPlaceGame"]["matchup"] = matchup(side(C, None, 3), None, None, is_bye=True)
    with pytest.raises(ContractError, match="/bracket/thirdPlaceGame/matchup"):
        validate(doc, "season")


def test_example_10_team_season_points_for_includes_a_manual_adjustment():
    # Spec: Matchup scores are shown without manual adjustments; points for includes them
    s = next(s for s in example_seasons().values() if s["teamCount"] == 10)
    regular = [p for p in s["weeklyResults"] if len(p["weeks"]) == 1]
    summed = {}
    for period in regular:
        for m in period["matchups"]:
            for sd in (m["home"], m["away"]):
                summed[sd["owner"]["slug"]] = summed.get(sd["owner"]["slug"], 0) + sd["score"]
    gaps = [e for e in s["standings"] if abs(e["pointsFor"] - summed[e["owner"]["slug"]]) > 0.005]
    assert len(gaps) == 1


def test_tie_has_no_winner():
    doc = season()
    doc["weeklyResults"][0]["matchups"][1]["winner"] = "home"
    with pytest.raises(ContractError, match="/weeklyResults/0/matchups/1"):
        validate(doc, "season")


def test_bracket_sides_need_a_seed():
    doc = season()
    del doc["bracket"]["rounds"][0]["matchups"][0]["home"]["seed"]
    with pytest.raises(ContractError, match="seed"):
        validate(doc, "season")


def test_unknown_fields_are_rejected():
    doc = copy.deepcopy(SHELF)
    doc["owners"][0]["espnId"] = "123"
    with pytest.raises(ContractError, match="espnId"):
        validate(doc, "trophyShelf")


# --- Example fixtures (contract/examples/): shared by both test seams ---

EXAMPLES = site_contract.EXAMPLES_DIR


def load_example(relpath):
    return json.loads((EXAMPLES / relpath).read_text(encoding="utf-8"))


def example_seasons():
    return {int(p.stem): load_example(f"seasons/{p.name}") for p in sorted((EXAMPLES / "seasons").glob("*.json"))}


def owner_refs(node):
    """Every ownerRef anywhere in a document."""
    if isinstance(node, dict):
        if set(node) == {"slug", "name"}:
            yield node
        for v in node.values():
            yield from owner_refs(v)
    elif isinstance(node, list):
        for v in node:
            yield from owner_refs(v)


def test_examples_validate_against_the_schema():
    validate(load_example("league.json"), "league")
    validate(load_example("trophy-shelf.json"), "trophyShelf")
    seasons = example_seasons()
    assert sorted(s["teamCount"] for s in seasons.values()) == [10, 12]
    for doc in seasons.values():
        validate(doc, "season")


def test_example_league_summary_lists_every_example_season():
    league = load_example("league.json")
    seasons = example_seasons()
    assert [s["year"] for s in league["seasons"]] == sorted(seasons)
    assert all(s["teamCount"] == seasons[s["year"]]["teamCount"] for s in league["seasons"])


def test_example_champion_is_the_latest_seasons_first_place():
    champ = load_example("league.json")["champion"]
    latest = example_seasons()[champ["year"]]
    assert champ["year"] == max(example_seasons())
    first = latest["podium"][0]
    assert (champ["owner"], champ["teamName"]) == (first["owner"], first["teamName"])


def test_example_owner_slugs_always_carry_the_same_name():
    docs = [load_example("league.json"), load_example("trophy-shelf.json"), *example_seasons().values()]
    names = {}
    for ref in (r for d in docs for r in owner_refs(d)):
        assert names.setdefault(ref["slug"], ref["name"]) == ref["name"], ref["slug"]


def test_example_trophy_shelf_covers_every_owner_and_includes_a_former_owner():
    shelf = load_example("trophy-shelf.json")["owners"]
    season_slugs = {r["slug"] for s in example_seasons().values() for r in owner_refs(s)}
    assert {e["owner"]["slug"] for e in shelf} == season_slugs
    assert any(e["isFormer"] for e in shelf)


def test_example_12_team_season_has_first_round_byes_and_a_third_place_game():
    s = next(s for s in example_seasons().values() if s["teamCount"] == 12)
    first_round = s["bracket"]["rounds"][0]["matchups"]
    assert [m["home"]["seed"] for m in first_round if m["isBye"]] == [1, 2]
    third = s["bracket"]["thirdPlaceGame"]
    assert third["matchupPeriod"] == s["bracket"]["rounds"][-1]["matchupPeriod"]
    assert not third["matchup"]["isBye"]


def test_example_10_team_season_has_two_week_playoff_rounds():
    s = next(s for s in example_seasons().values() if s["teamCount"] == 10)
    assert all(len(r["weeks"]) == 2 for r in s["bracket"]["rounds"])


def test_example_last_place_is_highest_seed_even_when_it_finishes_above_another_team():
    # The 10-team example's worst regular-season team wins a consolation game (spec: Last place)
    s = next(s for s in example_seasons().values() if s["teamCount"] == 10)
    worst = max(s["standings"], key=lambda e: e["playoffSeed"])
    assert s["lastPlace"]["owner"] == worst["owner"]
    assert worst["rank"] < s["teamCount"]
    assert s["lastPlace"]["punishment"] is None


def test_season_sections_from_later_tickets_are_optional_until_exported():
    # #9 and #10 add the bracket and weekly results to the export; until then they're optional
    doc = season()
    for key in ("bracket", "weeklyResults"):
        del doc[key]
    validate(doc, "season")


def test_season_requires_every_section_exported_so_far():
    for key in ("year", "teamCount", "dataTier", "podium", "lastPlace", "scoringFormat", "standings"):
        doc = season()
        del doc[key]
        with pytest.raises(ContractError, match=key):
            validate(doc, "season")
