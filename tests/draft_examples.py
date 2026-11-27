"""Draft examples: the Draft history example (contract/examples/draft.json), derived from the Season
examples, and a reference for Value over slot and Draft grades (GLOSSARY).

Plain Python, independent of the pipeline's SQL. test_site_contract.py uses it to check the examples
still agree with the Season examples and with the grading rules.

    uv run python tests/draft_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def derive() -> dict:
    """Every Season's first round, newest first; the all-time best and worst Picks; Best drafters."""
    seasons, all_picks, ranks = [], [], {}
    for path in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True):
        doc = json.loads(path.read_text(encoding="utf-8"))
        teams_by_slug = {o["owner"]["slug"]: o["teamName"] for o in doc["draft"]["order"]}
        for p in doc["draft"]["picks"]:
            if p["valueOverSlot"] is not None:
                all_picks.append(
                    {"year": doc["year"], "owner": p["owner"], "teamName": teams_by_slug[p["owner"]["slug"]]}
                    | {
                        k: p[k]
                        for k in ("overall", "round", "roundPick", "player", "positionalFinish", "valueOverSlot")
                    }
                )
        for g in doc["draft"]["grades"]:
            ranks.setdefault(g["owner"]["slug"], (g["owner"], []))[1].append(g["rank"])
        teams = {o["owner"]["slug"]: o["teamName"] for o in doc["draft"]["order"]}
        seasons.append(
            {
                "year": doc["year"],
                "teamCount": doc["teamCount"],
                "type": doc["draft"]["type"],
                "firstRound": [
                    {
                        "overall": p["overall"],
                        "owner": p["owner"],
                        "teamName": teams[p["owner"]["slug"]],
                        "player": p["player"],
                    }
                    for p in doc["draft"]["picks"]
                    if p["round"] == 1
                ],
            }
        )
    best = sorted(all_picks, key=lambda p: (-p["valueOverSlot"], p["year"], p["overall"]))[:10]
    worst = sorted(all_picks, key=lambda p: (p["valueOverSlot"], p["year"], p["overall"]))[:10]
    drafters = [
        {"owner": ref, "seasons": len(r), "averageRank": round(sum(r) / len(r), 2)} for ref, r in ranks.values()
    ]
    drafters.sort(key=lambda d: (d["averageRank"], d["owner"]["name"]))
    return {"seasons": seasons, "bestPicks": best, "worstPicks": worst, "bestDrafters": drafters}


def points_rank(value: float, values: list[float]) -> int:
    """Rank by points, ties sharing the better rank (SQL rank())."""
    return 1 + sum(v > value for v in values)


def value_over_slot(picks: list[dict]) -> dict[int, int | None]:
    """overall -> Value over slot: overall minus the rank by Season points among the drafted Picks.
    Picks with no Player recorded get None and are left out of the ranking."""
    recorded = [p["points"] for p in picks if p["player"] is not None]
    return {
        p["overall"]: None if p["player"] is None else p["overall"] - points_rank(p["points"], recorded) for p in picks
    }


def grades(draft: dict) -> list[dict]:
    """Draft grades: per Franchise the sum of Value over slot, ranked within the Season (ties share the
    better rank), ordered by rank then Owner name, with the best and worst Pick (earliest on a tie)."""
    vos = value_over_slot(draft["picks"])
    teams = {o["owner"]["slug"]: o for o in draft["order"]}
    totals = {
        slug: sum(vos[p["overall"]] for p in draft["picks"] if p["owner"]["slug"] == slug and p["player"])
        for slug in teams
    }
    out = []
    for slug, o in teams.items():
        mine = [p for p in draft["picks"] if p["owner"]["slug"] == slug and p["player"] is not None]

        def named(p):
            return {k: p[k] for k in ("overall", "round", "roundPick", "player")} | {"valueOverSlot": vos[p["overall"]]}

        out.append(
            {
                "rank": 1 + sum(t > totals[slug] for t in totals.values()),
                "owner": o["owner"],
                "teamName": o["teamName"],
                "total": totals[slug],
                "best": named(max(mine, key=lambda p: (vos[p["overall"]], -p["overall"]))),
                "worst": named(min(mine, key=lambda p: (vos[p["overall"]], p["overall"]))),
            }
        )
    return sorted(out, key=lambda g: (g["rank"], g["owner"]["name"]))


if __name__ == "__main__":
    out = EXAMPLES / "draft.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
