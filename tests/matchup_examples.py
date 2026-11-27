"""Derive the Matchups example (contract/examples/matchups.json) from the Season examples.

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


def derive() -> dict:
    """Every Season's championship, newest first."""
    seasons = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]
    return {"championships": [championship(s) for s in seasons]}


if __name__ == "__main__":
    out = EXAMPLES / "matchups.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
