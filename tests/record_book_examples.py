"""Derive the Record Book example (contract/examples/record-book.json) from the Season examples:
Last place history and the per-Owner tally.

A reference implementation in plain Python, independent of the pipeline's SQL. test_site_contract.py
uses it to check the example still agrees with the Season examples.

    uv run python tests/record_book_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
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


def _seasons() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]


def derive() -> dict:
    """record-book.json: Last place per Season (newest first) and the tally."""
    rows = [last_place_row(s) for s in _seasons()]
    return {"lastPlace": {"seasons": rows, "tally": tally(rows)}}


if __name__ == "__main__":
    out = EXAMPLES / "record-book.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
