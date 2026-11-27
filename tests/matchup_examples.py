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
    }


def derive() -> dict:
    """Every Season's championship (newest first) and the leaderboards."""
    seasons = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]
    return {"championships": [championship(s) for s in seasons], "leaderboards": leaderboards(seasons)}


if __name__ == "__main__":
    out = EXAMPLES / "matchups.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
