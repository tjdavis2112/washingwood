"""Derive the Record Book example (contract/examples/record-book.json) from the Season examples:
Season records, the All-time table, Last place history and the per-Owner tally.

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


def season_rows(season: dict) -> list[dict]:
    """Every Franchise-Season in a Season, from its standings."""
    rows = []
    for s in season["standings"]:
        r = {"year": season["year"], "owner": s["owner"], "teamName": s["teamName"], "record": s["record"]}
        r |= _rates(s["record"], s["pointsFor"])
        r["pointsAgainst"] = s["pointsAgainst"]
        r["pointsAgainstPerGame"] = _round(Decimal(str(s["pointsAgainst"])) / r["games"], 2)
        r["scoringFormat"] = season["scoringFormat"]["label"]
        rows.append(r)
    return rows


SEASON_RECORDS = [
    ("bestWinPct", "winPct", True),
    ("worstWinPct", "winPct", False),
    ("mostPointsFor", "pointsPerGame", True),
    ("fewestPointsFor", "pointsPerGame", False),
    ("mostPointsAgainst", "pointsAgainstPerGame", True),
]


def season_records(rows: list[dict]) -> dict:
    """Top 10 per record; ties go to the earlier Season, then Owner name."""
    return {
        key: sorted(rows, key=lambda r: (-r[field] if high else r[field], r["year"], r["owner"]["name"]))[:10]
        for key, field, high in SEASON_RECORDS
    }


def all_time(rows: list[dict], last_places: list[dict]) -> list[dict]:
    """One row per Owner, summed over their Seasons; wins descending, then name."""
    by_owner: dict[str, dict] = {}
    for r in rows:
        e = by_owner.setdefault(
            r["owner"]["slug"], {"owner": r["owner"], "seasons": 0, "w": 0, "l": 0, "t": 0, "pf": Decimal(0)}
        )
        e["seasons"] += 1
        e["w"] += r["record"]["wins"]
        e["l"] += r["record"]["losses"]
        e["t"] += r["record"]["ties"]
        e["pf"] += Decimal(str(r["pointsFor"]))
    out = []
    for slug, e in by_owner.items():
        record = {"wins": e["w"], "losses": e["l"], "ties": e["t"]}
        row = {"owner": e["owner"], "seasons": e["seasons"], "record": record}
        row |= _rates(record, float(e["pf"]))
        row["lastPlaces"] = sum(1 for lp in last_places if lp["owner"]["slug"] == slug)
        out.append(row)
    return sorted(out, key=lambda r: (-r["record"]["wins"], r["owner"]["name"]))


def _seasons() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]


def derive() -> dict:
    """record-book.json: Season records, the All-time table, Last place per Season (newest first) and the tally."""
    seasons = _seasons()
    rows = [r for s in seasons for r in season_rows(s)]
    last = [last_place_row(s) for s in seasons]
    return {
        "season": season_records(rows),
        "allTime": all_time(rows, last),
        "lastPlace": {"seasons": last, "tally": tally(last)},
    }


if __name__ == "__main__":
    out = EXAMPLES / "record-book.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
