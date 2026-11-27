"""Draft examples: the Draft history example (contract/examples/draft.json), derived from the Season
examples, and a reference for Value over slot, Points over expected and Draft grades (GLOSSARY).

Plain Python, independent of the pipeline's SQL. test_site_contract.py uses it to check the examples
still agree with the Season examples and with the grading rules.

    uv run python tests/draft_examples.py   # rewrite each Season's draft values, then draft.json
"""

from __future__ import annotations

import json
import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"

ALL_TIME_KEYS = (
    "overall",
    "round",
    "roundPick",
    "player",
    "points",
    "positionalFinish",
    "valueOverSlot",
    "pointsOverExpected",
)


def derive() -> dict:
    """Every Season's first round, newest first; the all-time Steals, Hits and Busts; Best drafters."""
    seasons, all_picks, ranks = [], [], {}
    for path in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True):
        doc = json.loads(path.read_text(encoding="utf-8"))
        teams_by_slug = {o["owner"]["slug"]: o["teamName"] for o in doc["draft"]["order"]}
        for p in doc["draft"]["picks"]:
            if p["pointsOverExpected"] is not None:
                all_picks.append(
                    {"year": doc["year"], "owner": p["owner"], "teamName": teams_by_slug[p["owner"]["slug"]]}
                    | {k: p[k] for k in ALL_TIME_KEYS}
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
    steals = sorted(all_picks, key=lambda p: (-p["valueOverSlot"], -p["points"], p["year"], p["overall"]))[:10]
    hits = sorted(all_picks, key=lambda p: (-p["pointsOverExpected"], -p["points"], p["year"], p["overall"]))[:10]
    busts = sorted(all_picks, key=lambda p: (p["pointsOverExpected"], p["points"], p["year"], p["overall"]))[:10]
    drafters = [
        {"owner": ref, "seasons": len(r), "averageRank": round(sum(r) / len(r), 2)} for ref, r in ranks.values()
    ]
    drafters.sort(key=lambda d: (d["averageRank"], d["owner"]["name"]))
    return {"seasons": seasons, "steals": steals, "hits": hits, "busts": busts, "bestDrafters": drafters}


def points_rank(value: float, values: list[float]) -> int:
    """Rank by points, ties sharing the better rank (SQL rank())."""
    return 1 + sum(v > value for v in values)


def value_over_slot(picks: list[dict]) -> dict[int, int | None]:
    """overall -> Value over slot: the Pick's order among the recorded Picks at its position, minus its
    finish by Season points among them (ties share the better finish). Picks with no Player recorded
    get None and are left out."""
    by_position: dict[str, list[dict]] = {}
    for p in sorted(picks, key=lambda p: p["overall"]):
        if p["player"] is not None:
            by_position.setdefault(p["player"]["position"], []).append(p)
    out: dict[int, int | None] = {p["overall"]: None for p in picks}
    for same in by_position.values():
        points = [p["points"] for p in same]
        for order, p in enumerate(same, start=1):
            out[p["overall"]] = order - points_rank(p["points"], points)
    return out


def points_above_replacement(pick: dict, replacement: list[dict]) -> Decimal:
    """Season points minus the position's Replacement points, floored at 0."""
    rep = {r["position"]: Decimal(str(r["points"])) for r in replacement}
    return max(Decimal(str(pick["points"])) - rep[pick["player"]["position"]], Decimal(0))


def round_expectations(drafts: list[dict]) -> dict[int, Decimal]:
    """Round -> the mean Points above replacement of every recorded Pick in that Round, across Seasons."""
    by_round: dict[int, list[Decimal]] = {}
    for d in drafts:
        for p in d["picks"]:
            if p["player"] is not None:
                by_round.setdefault(p["round"], []).append(points_above_replacement(p, d["replacement"]))
    return {rnd: sum(v) / len(v) for rnd, v in by_round.items()}


def points_over_expected(draft: dict, expectations: dict[int, Decimal]) -> dict[int, int | None]:
    """overall -> Points over expected: Points above replacement minus the Round's expectation, rounded
    to whole points (half away from zero, as SQL round()). Picks with no Player recorded get None."""
    out: dict[int, int | None] = {}
    for p in draft["picks"]:
        if p["player"] is None:
            out[p["overall"]] = None
            continue
        diff = points_above_replacement(p, draft["replacement"]) - expectations[p["round"]]
        out[p["overall"]] = int(diff.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return out


def grades(draft: dict, poe: dict[int, int | None]) -> list[dict]:
    """Draft grades: per Franchise the sum of Points over expected, ranked within the Season (ties share
    the better rank), ordered by rank then Owner name, with the best and worst Pick (earliest on a tie)."""
    teams = {o["owner"]["slug"]: o for o in draft["order"]}
    totals = {
        slug: sum(poe[p["overall"]] for p in draft["picks"] if p["owner"]["slug"] == slug and p["player"])
        for slug in teams
    }
    out = []
    for slug, o in teams.items():
        mine = [p for p in draft["picks"] if p["owner"]["slug"] == slug and p["player"] is not None]

        def named(p):
            return {k: p[k] for k in ("overall", "round", "roundPick", "player")} | {
                "pointsOverExpected": poe[p["overall"]]
            }

        out.append(
            {
                "rank": 1 + sum(t > totals[slug] for t in totals.values()),
                "owner": o["owner"],
                "teamName": o["teamName"],
                "total": totals[slug],
                "best": named(max(mine, key=lambda p: (poe[p["overall"]], -p["overall"]))),
                "worst": named(min(mine, key=lambda p: (poe[p["overall"]], p["overall"]))),
            }
        )
    return sorted(out, key=lambda g: (g["rank"], g["owner"]["name"]))


# Invented examples have no undrafted Players, so their Replacement level comes from the drafted ones: the
# finish follows the GLOSSARY rule for a 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / K / D/ST lineup, and the
# points are the drafted Player's at or nearest above that finish (the lowest-ranked one if none is).
EXAMPLE_STARTERS = {"QB": 1, "RB": 2.5, "WR": 2.5, "TE": 1, "K": 1, "D/ST": 1}


def example_replacement(doc: dict) -> list[dict]:
    picks = [p for p in doc["draft"]["picks"] if p["player"] is not None]
    out = []
    for pos in sorted({p["player"]["position"] for p in picks}):
        finish = math.ceil(doc["teamCount"] * EXAMPLE_STARTERS.get(pos, 1))
        same = [p for p in picks if p["player"]["position"] == pos]
        at_or_above = [p for p in same if p["positionalFinish"] <= finish] or same
        ref = min(at_or_above, key=lambda p: (-p["positionalFinish"], p["points"]))
        out.append({"position": pos, "finish": finish, "points": ref["points"]})
    return out


def write_season_values() -> None:
    """Rewrite each Season example's Replacement level, Points over expected and Draft grades."""
    paths = sorted((EXAMPLES / "seasons").glob("*.json"))
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    for doc in docs:
        old = doc["draft"]
        doc["draft"] = {k: v for k, v in old.items() if k not in ("replacement", "grades")}
        doc["draft"]["replacement"] = example_replacement(doc)
        doc["draft"]["grades"] = old["grades"]
    expectations = round_expectations([doc["draft"] for doc in docs])
    for path, doc in zip(paths, docs, strict=True):
        d = doc["draft"]
        poe = points_over_expected(d, expectations)
        for p in d["picks"]:
            p["pointsOverExpected"] = poe[p["overall"]]
        d["grades"] = grades(d, poe)
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_season_values()
    out = EXAMPLES / "draft.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote the Season examples' draft values and {out.name}")
