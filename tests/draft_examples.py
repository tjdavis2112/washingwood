"""Derive the Draft history example (contract/examples/draft.json) from the Season examples.

A reference implementation in plain Python, independent of the pipeline's SQL. test_site_contract.py
uses it to check the example still agrees with the Season examples.

    uv run python tests/draft_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def derive() -> dict:
    """Every Season's first round, newest first."""
    seasons = []
    for path in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True):
        doc = json.loads(path.read_text(encoding="utf-8"))
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
    return {"seasons": seasons}


if __name__ == "__main__":
    out = EXAMPLES / "draft.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
