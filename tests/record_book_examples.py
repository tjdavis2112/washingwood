"""Derive the Record Book example (contract/examples/record-book.json) from the Season and Box score
examples: Week records, Season records, the All-time table, Last place history and the per-Owner tally.

A reference implementation in plain Python, independent of the pipeline's SQL. test_site_contract.py
uses it to check the example still agrees with the Season examples.

    uv run python tests/record_book_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def last_place_row(season: dict) -> dict:
    """A Season's Last place: the Season document's lastPlace, plus points for from its standings row."""
    last = season["lastPlace"]
    (row,) = [s for s in season["standings"] if s["owner"]["slug"] == last["owner"]["slug"]]
    return {
        "year": season["year"],
        "owner": last["owner"],
        "teamName": last["teamName"],
        "record": last["record"],
        "pointsFor": row["pointsFor"],
        "scoringFormat": season["scoringFormat"]["label"],
    }


def tally(rows: list[dict]) -> list[dict]:
    """Every Owner with a Last place: count descending, then name; their Seasons oldest first."""
    by_owner: dict[str, dict] = {}
    for r in rows:
        entry = by_owner.setdefault(r["owner"]["slug"], {"owner": r["owner"], "count": 0, "years": []})
        entry["count"] += 1
        entry["years"].append(r["year"])
    for entry in by_owner.values():
        entry["years"].sort()
    return sorted(by_owner.values(), key=lambda e: (-e["count"], e["owner"]["name"]))


def _round(x: Decimal, places: int) -> float:
    """Round half away from zero, as Postgres round() does on numeric."""
    return float(x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _rates(record: dict, points_for: float) -> dict:
    games = record["wins"] + record["losses"] + record["ties"]
    return {
        "games": games,
        "winPct": _round((record["wins"] + Decimal(record["ties"]) / 2) / games, 4),
        "pointsFor": points_for,
        "pointsPerGame": _round(Decimal(str(points_for)) / games, 2),
    }


def bench_points(week: dict) -> Decimal:
    """A side's Bench points for one Week: BE-slot points (IR excluded); a Player who didn't play counts 0."""
    return sum((Decimal(str(e["points"] or 0)) for e in week["bench"] if e["slot"] == "BE"), Decimal(0))


def season_bench(box: dict | None) -> dict[str, Decimal]:
    """Owner slug -> Bench points over the Season's regular-season Weeks; empty without Box scores."""
    totals: dict[str, Decimal] = {}
    for m in (box or {"matchups": []})["matchups"]:
        if m["kind"] != "regular":
            continue
        for side in (m["home"], m.get("away")):
            if side:
                slug = side["owner"]["slug"]
                totals[slug] = totals.get(slug, Decimal(0)) + sum((bench_points(w) for w in side["weeks"]), Decimal(0))
    return totals


def week_rows(season: dict, box: dict | None) -> list[dict]:
    """Both sides of every Counted Matchup (GLOSSARY) in a Box score example: regular-season and
    winners'-bracket Matchups played in a single Week. Consolation Matchups, the Third-place game, byes
    and two-week rounds are left out."""
    seeds = {s["owner"]["slug"]: s["playoffSeed"] for s in season["standings"]}
    rows = []
    for m in (box or {"matchups": []})["matchups"]:
        if m["kind"] not in ("regular", "playoff") or len(m["weeks"]) != 1 or not m.get("away"):
            continue

        def side(x, m=m):
            seed = seeds[x["owner"]["slug"]] if m["kind"] == "playoff" else None
            return {"owner": x["owner"], "teamName": x["teamName"], "score": x["score"], "seed": seed}

        for me, other, who in ((m["home"], m["away"], "home"), (m["away"], m["home"], "away")):
            rows.append(
                {
                    "year": season["year"],
                    "matchupPeriod": m["matchupPeriod"],
                    "week": m["weeks"][0],
                    "kind": m["kind"],
                    "team": side(me),
                    "opponent": side(other),
                    "result": "tie" if m["isTie"] else "win" if m["winner"] == who else "loss",
                    "benchPoints": float(bench_points(me["weeks"][0])),
                    "scoringFormat": season["scoringFormat"]["label"],
                }
            )
    return rows


def week_records(rows: list[dict]) -> dict:
    """Top 10 per Week record; ties go to the earlier Season, then Week, then Owner name."""

    def top(candidates, value, high):
        return sorted(
            candidates,
            key=lambda r: (-value(r) if high else value(r), r["year"], r["week"], r["team"]["owner"]["name"]),
        )[:10]

    return {
        "mostPointsInLoss": top([r for r in rows if r["result"] == "loss"], lambda r: r["team"]["score"], True),
        "fewestPointsInWin": top([r for r in rows if r["result"] == "win"], lambda r: r["team"]["score"], False),
        "mostBenchPoints": top(rows, lambda r: r["benchPoints"], True),
    }


def season_rows(season: dict, box: dict | None = None) -> list[dict]:
    """Every Franchise-Season in a Season, from its standings, with Bench points from its Box scores."""
    bench = season_bench(box)
    rows = []
    for s in season["standings"]:
        r = {"year": season["year"], "owner": s["owner"], "teamName": s["teamName"], "record": s["record"]}
        r |= _rates(s["record"], s["pointsFor"])
        r["pointsAgainst"] = s["pointsAgainst"]
        r["pointsAgainstPerGame"] = _round(Decimal(str(s["pointsAgainst"])) / r["games"], 2)
        slug = s["owner"]["slug"]
        r["benchPoints"] = float(bench[slug]) if slug in bench else None
        r["scoringFormat"] = season["scoringFormat"]["label"]
        rows.append(r)
    return rows


SEASON_RECORDS = [
    ("bestWinPct", "winPct", True),
    ("worstWinPct", "winPct", False),
    ("mostPointsFor", "pointsPerGame", True),
    ("fewestPointsFor", "pointsPerGame", False),
    ("mostPointsAgainst", "pointsAgainstPerGame", True),
    ("mostBenchPoints", "benchPoints", True),
]


def season_records(rows: list[dict]) -> dict:
    """Top 10 per record (Bench points: Seasons with lineups only); ties go to the earlier Season, then
    Owner name."""
    return {
        key: sorted(
            [r for r in rows if r[field] is not None],
            key=lambda r: (-r[field] if high else r[field], r["year"], r["owner"]["name"]),
        )[:10]
        for key, field, high in SEASON_RECORDS
    }


def all_time(rows: list[dict], last_places: list[dict]) -> list[dict]:
    """One row per Owner, summed over their Seasons; wins descending, then name."""
    by_owner: dict[str, dict] = {}
    for r in rows:
        e = by_owner.setdefault(
            r["owner"]["slug"],
            {"owner": r["owner"], "seasons": 0, "w": 0, "l": 0, "t": 0, "pf": Decimal(0), "bench": None},
        )
        e["seasons"] += 1
        e["w"] += r["record"]["wins"]
        e["l"] += r["record"]["losses"]
        e["t"] += r["record"]["ties"]
        e["pf"] += Decimal(str(r["pointsFor"]))
        if r["benchPoints"] is not None:
            e["bench"] = (e["bench"] or Decimal(0)) + Decimal(str(r["benchPoints"]))
    out = []
    for slug, e in by_owner.items():
        record = {"wins": e["w"], "losses": e["l"], "ties": e["t"]}
        row = {"owner": e["owner"], "seasons": e["seasons"], "record": record}
        row |= _rates(record, float(e["pf"]))
        row["benchPoints"] = None if e["bench"] is None else float(e["bench"])
        row["lastPlaces"] = sum(1 for lp in last_places if lp["owner"]["slug"] == slug)
        out.append(row)
    return sorted(out, key=lambda r: (-r["record"]["wins"], r["owner"]["name"]))


def _seasons() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]


def _box_scores(year: int) -> dict | None:
    path = EXAMPLES / "box-scores" / f"{year}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def derive() -> dict:
    """record-book.json: Week and Season records, the All-time table, Last place per Season (newest first)
    and the tally."""
    seasons = _seasons()
    boxes = {s["year"]: _box_scores(s["year"]) for s in seasons}
    rows = [r for s in seasons for r in season_rows(s, boxes[s["year"]])]
    last = [last_place_row(s) for s in seasons]
    return {
        "week": week_records([r for s in seasons for r in week_rows(s, boxes[s["year"]])]),
        "season": season_records(rows),
        "allTime": all_time(rows, last),
        "lastPlace": {"seasons": last, "tally": tally(last)},
    }


if __name__ == "__main__":
    out = EXAMPLES / "record-book.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
