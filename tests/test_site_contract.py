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
        "draft": draft(),
    }


def draft():
    """A 2-round snake Draft for the tiny Season; the last Pick has no Player recorded."""
    order = [D, C, B, A]
    picks = []
    for rnd in (1, 2):
        for i, o in enumerate(order if rnd == 1 else list(reversed(order))):
            overall = (rnd - 1) * 4 + i + 1
            player = {"name": f"Example Player {overall}", "position": "RB", "nflTeam": "KC"}
            picks.append({"overall": overall, "round": rnd, "roundPick": i + 1, "owner": o, "player": player})
    picks[-1]["player"] = None
    return {
        "type": "offline",
        "rounds": 2,
        "order": [{"slot": i + 1, "owner": o, "teamName": TEAM[o["slug"]]} for i, o in enumerate(order)],
        "picks": picks,
        "note": "Drafted offline and entered by hand. 1 pick wasn't recorded.",
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
    docs = [
        load_example("league.json"),
        load_example("trophy-shelf.json"),
        load_example("owners.json"),
        *example_seasons().values(),
        *example_owners().values(),
    ]
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


def test_season_requires_every_section():
    keys = (
        "year",
        "teamCount",
        "dataTier",
        "podium",
        "lastPlace",
        "scoringFormat",
        "standings",
        "bracket",
        "weeklyResults",
        "draft",
    )
    for key in keys:
        doc = season()
        del doc[key]
        with pytest.raises(ContractError, match=key):
            validate(doc, "season")


# --- Owner index and Owner documents (#13) ---


def example_owners():
    return {p.stem: load_example(f"owners/{p.name}") for p in sorted((EXAMPLES / "owners").glob("*.json"))}


def test_owner_examples_validate_and_are_named_by_slug():
    validate(load_example("owners.json"), "ownerIndex")
    for slug, doc in example_owners().items():
        validate(doc, "owner")
        assert doc["owner"]["slug"] == slug


def test_owner_examples_agree_with_the_season_and_shelf_examples():
    # Re-derived in plain Python from the Season and trophy-shelf examples (tests/owner_examples.py)
    from owner_examples import derive

    index, owners = derive()
    assert load_example("owners.json") == index
    assert example_owners() == owners


def test_owner_index_example_follows_the_trophy_shelf():
    shelf = load_example("trophy-shelf.json")["owners"]
    index = load_example("owners.json")["owners"]
    assert [e["owner"] for e in index] == [e["owner"] for e in shelf]
    assert {e["owner"]["slug"] for e in index} == set(example_owners())
    assert any(e["isFormer"] for e in index)


def test_owner_example_head_to_head_is_symmetric_and_sums_to_the_career_record():
    owners = example_owners()
    for slug, doc in owners.items():
        regular = {k: sum(h["regularSeason"][k] for h in doc["headToHead"]) for k in ("wins", "losses", "ties")}
        assert regular == doc["career"]["regularSeason"], slug
        for h in doc["headToHead"]:
            back = next(b for b in owners[h["opponent"]["slug"]]["headToHead"] if b["opponent"]["slug"] == slug)
            for part in ("regularSeason", "playoffs"):
                assert (h[part]["wins"], h[part]["ties"]) == (back[part]["losses"], back[part]["ties"])


def owner_doc():
    return copy.deepcopy(example_owners()["quinn-harrow"])


def test_head_to_head_rows_need_at_least_one_meeting():
    doc = owner_doc()
    doc["headToHead"][0]["meetings"] = 0
    with pytest.raises(ContractError, match="/headToHead/0/meetings"):
        validate(doc, "owner")


def test_podium_place_is_1_2_3_or_null():
    doc = owner_doc()
    doc["seasons"][0]["podiumPlace"] = 4
    with pytest.raises(ContractError, match="/seasons/0/podiumPlace"):
        validate(doc, "owner")


def test_owner_index_entry_needs_a_regular_season_record():
    doc = load_example("owners.json")
    del doc["owners"][0]["regularSeason"]
    with pytest.raises(ContractError, match="regularSeason"):
        validate(doc, "ownerIndex")


# --- Draft (#25) ---


def test_draft_type_must_be_snake_or_offline():
    doc = season()
    doc["draft"]["type"] = "auction"
    with pytest.raises(ContractError, match="/draft/type"):
        validate(doc, "season")


def test_a_pick_player_needs_name_position_and_nfl_team_or_is_null():
    doc = season()
    del doc["draft"]["picks"][0]["player"]["nflTeam"]
    with pytest.raises(ContractError, match="/draft/picks/0/player"):
        validate(doc, "season")
    doc = season()
    doc["draft"]["picks"][0]["player"]["nflTeam"] = None  # a free agent
    validate(doc, "season")


def test_picks_never_carry_platform_ids():
    doc = season()
    doc["draft"]["picks"][0]["memberId"] = "{X}"
    with pytest.raises(ContractError, match="memberId"):
        validate(doc, "season")


def test_example_drafts_are_full_snake_boards_of_that_seasons_owners():
    for year, doc in example_seasons().items():
        d = doc["draft"]
        n = doc["teamCount"]
        assert [o["slot"] for o in d["order"]] == list(range(1, n + 1)), year
        assert {o["owner"]["slug"] for o in d["order"]} == {r["owner"]["slug"] for r in doc["standings"]}, year
        teams = {r["owner"]["slug"]: r["teamName"] for r in doc["standings"]}
        assert all(o["teamName"] == teams[o["owner"]["slug"]] for o in d["order"]), year
        assert [p["overall"] for p in d["picks"]] == list(range(1, n * d["rounds"] + 1)), year
        slot = {o["owner"]["slug"]: o["slot"] for o in d["order"]}
        for p in d["picks"]:
            assert p["overall"] == (p["round"] - 1) * n + p["roundPick"], (year, p)
            expected = p["roundPick"] if p["round"] % 2 else n + 1 - p["roundPick"]
            assert slot[p["owner"]["slug"]] == expected, (year, p)


def test_example_2018_draft_is_offline_with_an_unrecorded_pick_and_2020_has_a_dst():
    seasons = example_seasons()
    d2018, d2020 = seasons[2018]["draft"], seasons[2020]["draft"]
    assert d2018["type"] == "offline"
    assert d2018["note"]
    assert any(p["player"] is None for p in d2018["picks"])
    assert d2020["type"] == "snake"
    assert d2020["note"] is None
    assert all(p["player"] is not None for p in d2020["picks"])
    assert {"D/ST", "K"} <= {p["player"]["position"] for p in d2020["picks"]}


def test_owner_example_drafts_start_with_the_round_1_pick_at_their_draft_slot():
    for slug, doc in example_owners().items():
        assert [d["year"] for d in doc["draft"]] == [s["year"] for s in doc["seasons"]], slug
        for d in doc["draft"]:
            first = d["picks"][0]
            assert (first["round"], first["roundPick"]) == (1, d["slot"]), (slug, d["year"])
            assert [p["round"] for p in d["picks"]] == sorted(p["round"] for p in d["picks"]), (slug, d["year"])


# --- Draft history (#27) ---


def test_draft_history_example_validates_and_agrees_with_the_season_examples():
    from draft_examples import derive

    doc = load_example("draft.json")
    validate(doc, "draft")
    assert doc == derive()
    assert [s["year"] for s in doc["seasons"]] == sorted(example_seasons(), reverse=True)
    for s in doc["seasons"]:
        assert len(s["firstRound"]) == s["teamCount"], s["year"]


def test_draft_history_rejects_unknown_fields_on_a_pick():
    doc = load_example("draft.json")
    doc["seasons"][0]["firstRound"][0]["memberId"] = "{X}"
    with pytest.raises(ContractError, match="memberId"):
        validate(doc, "draft")
