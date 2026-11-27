"""Derive the Matchups example (contract/examples/matchups.json) from the Season examples: championship
cards and the leaderboards over Counted Matchups.

A reference implementation in plain Python, independent of the pipeline's SQL. test_site_contract.py
uses it to check the example still agrees with the Season examples.

    uv run python tests/matchup_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def championship(season: dict) -> dict:
    """A Season's championship card: the last bracket round's single Matchup, winner first."""
    final_round = season["bracket"]["rounds"][-1]
    (final,) = final_round["matchups"]
    champion, runner_up = (
        (final["home"], final["away"]) if final["winner"] == "home" else (final["away"], final["home"])
    )
    return {
        "year": season["year"],
        "matchupPeriod": final_round["matchupPeriod"],
        "weeks": final_round["weeks"],
        "champion": champion,
        "runnerUp": runner_up,
        "margin": round(champion["score"] - runner_up["score"], 2),
    }


def counted_matchups(season: dict) -> list[tuple[str, list[int], int, dict, dict, str | None, bool]]:
    """Counted Matchups (GLOSSARY): (kind, weeks, period, home, away, winner, isTie). Regular season from
    the weekly results (periods before the first bracket round); playoffs from the bracket rounds (the
    Third-place game is separate and not counted). Byes and two-week rounds are left out. Regular-season
    sides get seed None."""
    first_round = season["bracket"]["rounds"][0]["matchupPeriod"]
    out = []
    for period in season["weeklyResults"]:
        if period["matchupPeriod"] >= first_round or len(period["weeks"]) != 1:
            continue
        for m in period["matchups"]:
            if not m["isBye"]:
                home, away = ({**m[k], "seed": None} for k in ("home", "away"))
                out.append(("regular", period["weeks"], period["matchupPeriod"], home, away, m["winner"], m["isTie"]))
    for rnd in season["bracket"]["rounds"]:
        if len(rnd["weeks"]) != 1:
            continue
        for m in rnd["matchups"]:
            if not m["isBye"]:
                out.append(
                    ("playoff", rnd["weeks"], rnd["matchupPeriod"], m["home"], m["away"], m["winner"], m["isTie"])
                )
    return out


def leaderboards(seasons: list[dict]) -> dict:
    """Top-10 lists over every Season's Counted Matchups; ties by Season, Week, then Owner name."""

    def side(s):
        return {"owner": s["owner"], "teamName": s["teamName"], "score": s["score"], "seed": s["seed"]}

    games, sides = [], []
    for season in seasons:
        label = season["scoringFormat"]["label"]
        for kind, weeks, period, home, away, winner, is_tie in counted_matchups(season):
            h, a = side(home), side(away)
            win, lose = (a, h) if winner == "away" else (h, a)
            base = {"year": season["year"], "matchupPeriod": period, "weeks": weeks, "kind": kind}
            games.append(
                base
                | {"winner": win, "loser": lose, "isTie": is_tie, "margin": round(win["score"] - lose["score"], 2)}
                | {"scoringFormat": label}
            )
            for team, opp in ((h, a), (a, h)):
                result = "tie" if is_tie else ("win" if team is win else "loss")
                sides.append(base | {"team": team, "opponent": opp, "result": result, "scoringFormat": label})

    def when(r, who):
        return (r["year"], r["matchupPeriod"], r[who]["owner"]["name"])

    upsets = [
        g | {"seedGap": g["winner"]["seed"] - g["loser"]["seed"]}
        for g in games
        if g["kind"] == "playoff" and not g["isTie"] and g["winner"]["seed"] > g["loser"]["seed"]
    ]
    return {
        "blowouts": sorted(games, key=lambda g: (-g["margin"], *when(g, "winner")))[:10],
        "closestGames": sorted(games, key=lambda g: (g["margin"], *when(g, "winner")))[:10],
        "highestScores": sorted(sides, key=lambda r: (-r["team"]["score"], *when(r, "team")))[:10],
        "lowestScores": sorted(sides, key=lambda r: (r["team"]["score"], *when(r, "team")))[:10],
        "playoffUpsets": sorted(upsets, key=lambda g: (-g["seedGap"], -g["margin"], *when(g, "winner")))[:10],
        "projectionUpsets": projection_upsets(games),
    }


def projection_upsets(games: list[dict]) -> list[dict]:
    """Counted Matchups won by the side with the lower Projected score, from the Box score examples'
    projections (Seasons without a Box score file have none); by projected deficit, then Season, Week,
    winner name."""
    projected = {}
    for path in (EXAMPLES / "box-scores").glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for m in doc["matchups"]:
            for k in ("home", "away"):
                projected[(doc["year"], m["matchupPeriod"], m[k]["owner"]["slug"])] = m[k]["projected"]
    rows = []
    for g in games:
        if g["isTie"]:
            continue
        win = projected.get((g["year"], g["matchupPeriod"], g["winner"]["owner"]["slug"]))
        lose = projected.get((g["year"], g["matchupPeriod"], g["loser"]["owner"]["slug"]))
        if win is not None and lose is not None and win < lose:
            rows.append(g | {"winnerProjected": win, "loserProjected": lose, "projectedDeficit": round(lose - win, 2)})
    key = lambda g: (-g["projectedDeficit"], g["year"], g["matchupPeriod"], g["winner"]["owner"]["name"])  # noqa: E731
    return sorted(rows, key=key)[:10]


def _seasons() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]


def _pair_key(m: dict) -> frozenset:
    return frozenset((m["home"]["owner"]["slug"], m["away"]["owner"]["slug"]))


def rivalries(seasons: list[dict]) -> dict[str, dict]:
    """Rivalry documents keyed "<a>-vs-<b>": every played game between two Owners, newest first, classed
    from the weekly results (regular season before the first bracket round; then bracket, Third-place
    game or consolation). Records follow the head-to-head rules: regular season plus bracket games."""
    pairs: dict[tuple[str, str], dict] = {}
    for season in sorted(seasons, key=lambda x: x["year"], reverse=True):
        first_round = season["bracket"]["rounds"][0]["matchupPeriod"]
        bracket = {
            (r["matchupPeriod"], _pair_key(m))
            for r in season["bracket"]["rounds"]
            for m in r["matchups"]
            if not m["isBye"]
        }
        third = season["bracket"]["thirdPlaceGame"]
        third_key = (third["matchupPeriod"], _pair_key(third["matchup"]))
        for period in sorted(season["weeklyResults"], key=lambda p: p["matchupPeriod"], reverse=True):
            for m in period["matchups"]:
                if m["isBye"]:
                    continue
                key = (period["matchupPeriod"], _pair_key(m))
                if period["matchupPeriod"] < first_round:
                    kind = "regular"
                elif key in bracket:
                    kind = "playoff"
                elif key == third_key:
                    kind = "thirdPlace"
                else:
                    kind = "consolation"
                ordered = sorted(["home", "away"], key=lambda k: m[k]["owner"]["slug"])
                refs = [m[k]["owner"] for k in ordered]
                doc = pairs.setdefault((refs[0]["slug"], refs[1]["slug"]), {"owners": refs, "games": []})
                scores = [m[k]["score"] for k in ordered]
                doc["games"].append(
                    {
                        "year": season["year"],
                        "matchupPeriod": period["matchupPeriod"],
                        "weeks": period["weeks"],
                        "kind": kind,
                        "inRecord": kind in ("regular", "playoff"),
                        "teams": [{"teamName": m[k]["teamName"], "score": m[k]["score"]} for k in ordered],
                        "winner": None if m["isTie"] else ordered.index(m["winner"]),
                        "isTie": m["isTie"],
                        "margin": round(abs(scores[0] - scores[1]), 2),
                    }
                )
    docs = {}
    for (a, b), doc in sorted(pairs.items()):
        games, sides = doc["games"], []
        for i, ref in enumerate(doc["owners"]):
            regular = {"wins": 0, "losses": 0, "ties": 0}
            playoffs = {"wins": 0, "losses": 0, "ties": 0}
            for g in games:
                if g["inRecord"]:
                    rec = regular if g["kind"] == "regular" else playoffs
                    rec["ties" if g["isTie"] else "wins" if g["winner"] == i else "losses"] += 1
            wins = [g for g in games if g["inRecord"] and g["winner"] == i]
            best = min(wins, key=lambda g: (-g["margin"], g["year"], g["matchupPeriod"])) if wins else None
            sides.append({"owner": ref, "regularSeason": regular, "playoffs": playoffs, "biggestWin": best})
        meetings = sum(g["inRecord"] for g in games)
        if meetings:
            docs[f"{a}-vs-{b}"] = {"sides": sides, "meetings": meetings, "games": games}
    return docs


def rivalry_grid(docs: dict[str, dict]) -> dict:
    """Owners in Owner-index order (owners.json) and every pair's combined record, both directions."""
    owners = [e["owner"] for e in json.loads((EXAMPLES / "owners.json").read_text(encoding="utf-8"))["owners"]]
    order = {o["slug"]: i for i, o in enumerate(owners)}
    records = []
    for doc in docs.values():
        for i in (0, 1):
            me, them = doc["sides"][i], doc["sides"][1 - i]
            rs, po = me["regularSeason"], me["playoffs"]
            totals = {k: rs[k] + po[k] for k in ("wins", "losses", "ties")}
            records.append({"owner": me["owner"]["slug"], "opponent": them["owner"]["slug"], **totals})
    records.sort(key=lambda r: (order[r["owner"]], order[r["opponent"]]))
    return {"owners": owners, "records": records}


def derive() -> dict:
    """matchups.json: every Season's championship (newest first), the leaderboards and the rivalry grid."""
    seasons = _seasons()
    return {
        "championships": [championship(s) for s in seasons],
        "leaderboards": leaderboards(seasons),
        "rivalryGrid": rivalry_grid(rivalries(seasons)),
    }


def derive_rivalries() -> dict[str, dict]:
    return rivalries(_seasons())


if __name__ == "__main__":
    out = EXAMPLES / "matchups.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    folder = EXAMPLES / "rivalries"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.json"):
        old.unlink()
    docs = derive_rivalries()
    for pair, doc in docs.items():
        (folder / f"{pair}.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"wrote {out.name} and {len(docs)} Rivalry documents")
