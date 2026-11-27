"""Invent the Box score examples (contract/examples/box-scores/<year>.json) from the Season examples.

Unlike the other example scripts this one invents data, deterministically: each side's lineup uses
the Owner's drafted Players from that Season's example draft (topped up with invented pickups), and
the starters' points split the side's score for each Week exactly, the rule the loader enforces on the
real archive. test_site_contract.py checks the examples against the Season examples and that rule.

    uv run python tests/box_score_examples.py   # rewrite the examples
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"
SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "D/ST", "K"]
FLEX_OK = {"RB", "WR", "TE"}
WEIGHT = {"QB": 1.3, "RB": 1.1, "WR": 1.1, "TE": 0.8, "FLEX": 0.9, "D/ST": 0.6, "K": 0.6}


def _noise(*parts) -> float:
    """A deterministic number in [0, 1) from the parts."""
    return int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0x100000000


def _kind(season: dict, period: int, home: str, away: str) -> str:
    first_round = season["bracket"]["rounds"][0]["matchupPeriod"]
    if period < first_round:
        return "regular"
    pair = {home, away}
    for r in season["bracket"]["rounds"]:
        for m in r["matchups"]:
            if (
                r["matchupPeriod"] == period
                and not m["isBye"]
                and {m["home"]["owner"]["slug"], m["away"]["owner"]["slug"]} == pair
            ):
                return "playoff"
    third = season["bracket"]["thirdPlaceGame"]
    tm = third["matchup"]
    if third["matchupPeriod"] == period and {tm["home"]["owner"]["slug"], tm["away"]["owner"]["slug"]} == pair:
        return "thirdPlace"
    return "consolation"


def _roster(season: dict, slug: str) -> list[dict]:
    """The Owner's Players: drafted that Season, then invented pickups."""
    picks = [p["player"] for p in season["draft"]["picks"] if p["owner"]["slug"] == slug and p["player"]]
    pickups = [
        {"name": f"Pickup {slug.split('-')[0].title()} {i}", "position": pos, "nflTeam": "FA" if i % 5 == 0 else "NYJ"}
        for i, pos in enumerate(["QB", "RB", "RB", "WR", "WR", "TE", "D/ST", "K", "RB", "WR", "WR", "TE"], start=1)
    ]
    return [dict(p) for p in picks] + pickups


def _lineup(season: dict, slug: str, week: int, total: float) -> dict:
    """Starters by slot from the roster template, the rest on the bench; points split `total` exactly."""
    template = [s for s in season["scoringFormat"]["rosterSlots"] if s["slot"] not in ("BE", "IR")]
    bench_size = next((s["count"] for s in season["scoringFormat"]["rosterSlots"] if s["slot"] == "BE"), 0)
    pool = _roster(season, slug)
    starters, used = [], set()
    for slot in SLOT_ORDER:
        for _ in range(next((s["count"] for s in template if s["slot"] == slot), 0)):
            ok = FLEX_OK if slot == "FLEX" else {slot}
            player = next(p for i, p in enumerate(pool) if i not in used and p["position"] in ok)
            used.add(pool.index(player))
            starters.append((slot, player))
    bench = [p for i, p in enumerate(pool) if i not in used][:bench_size]
    weights = [WEIGHT[slot] * (0.6 + _noise(season["year"], slug, week, i)) for i, (slot, _) in enumerate(starters)]
    shares = [round(total * w / sum(weights), 2) for w in weights]
    shares[0] = round(total - sum(shares[1:]), 2)  # the QB takes the rounding, so the sum is exact

    def entry(slot, p, pts, k):
        proj = round(pts * (0.8 + 0.4 * _noise("proj", season["year"], slug, week, k)), 2)
        return {
            "slot": slot,
            "name": p["name"],
            "position": p["position"],
            "nflTeam": p["nflTeam"],
            "points": pts,
            "projected": proj,
        }

    return {
        "week": week,
        "starters": [entry(slot, p, pts, i) for i, ((slot, p), pts) in enumerate(zip(starters, shares, strict=True))],
        "bench": [
            entry("BE", p, round(20 * _noise("bench", season["year"], slug, week, i), 2), 100 + i)
            for i, p in enumerate(bench)
        ],
        "emptySlots": [],
    }


def derive(season: dict) -> dict:
    matchups = []
    for period in season["weeklyResults"]:
        weeks = period["weeks"]
        for m in period["matchups"]:
            if m["isBye"]:
                continue
            sides = {}
            for k in ("home", "away"):
                s = m[k]
                # A two-week round's score is split between its Weeks
                per_week = [round(s["score"] / len(weeks), 2)] * (len(weeks) - 1)
                per_week.append(round(s["score"] - sum(per_week), 2))
                week_docs = [
                    _lineup(season, s["owner"]["slug"], w, pts) for w, pts in zip(weeks, per_week, strict=True)
                ]
                sides[k] = {
                    "owner": s["owner"],
                    "teamName": s["teamName"],
                    "score": s["score"],
                    "projected": round(sum(e["projected"] for w in week_docs for e in w["starters"]), 2),
                    "adjustment": 0,
                    "weeks": week_docs,
                }
            kind = _kind(season, period["matchupPeriod"], m["home"]["owner"]["slug"], m["away"]["owner"]["slug"])
            matchups.append(
                {"matchupPeriod": period["matchupPeriod"], "weeks": weeks, "kind": kind, **sides,
                 "winner": m["winner"], "isTie": m["isTie"]}
            )  # fmt: skip
    return {"year": season["year"], "matchups": matchups}


if __name__ == "__main__":
    folder = EXAMPLES / "box-scores"
    folder.mkdir(exist_ok=True)
    for path in sorted((EXAMPLES / "seasons").glob("*.json")):
        doc = derive(json.loads(path.read_text(encoding="utf-8")))
        (folder / path.name).write_text(
            json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"wrote box-scores/{path.name}: {len(doc['matchups'])} Matchups")
