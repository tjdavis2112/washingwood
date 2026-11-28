"""Derive the Hall of Fame example (contract/examples/hall-of-fame.json): invented Player seasons, inducted.

A reference implementation in plain Python, independent of the pipeline's SQL. The Player seasons below are
invented (ADR-0007); Owners and team names come from the Season examples so links resolve. Each Player has
his Season points, Positional finish and, per Owner who rostered him, a Week-by-Week log: points as a
starter, or None for a Week on the bench. The rules applied here are the ones the pipeline follows
(ADR-0009, GLOSSARY: Induction bar):

- Points above replacement = Season points minus the position's Replacement points that Season (the Season
  example's draft.replacement), never below 0;
- Dominant: Points above replacement at or above PAR_BAR (washingwood.hall_of_fame);
- credited to the Owner he scored the most starter points for; a tie goes to the earlier acquisition (the
  Owner whose log starts first);
- a Player who never started for anyone is not eligible;
- inductees: newest Season first, then highest Points above replacement, then Player name.

test_site_contract.py checks the example still equals derive().

    uv run python tests/hall_of_fame_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from pathlib import Path

from washingwood.hall_of_fame import PAR_BAR

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def _log(first: int, last: int, points: float, *, bench: tuple[int, ...] = ()) -> dict[int, float | None]:
    """A steady weekly log: `points` each Week from `first` to `last`, None on the bench Weeks."""
    return {w: None if w in bench else points for w in range(first, last + 1)}


# (year, name, position, NFL team, Season points, Positional finish, [(owner slug, weekly log), ...])
# fmt: off
PLAYER_SEASONS = [
    (2020, "Bodhi Lanark", "RB", "DAL", 362.4, 1, [("cass-imber", _log(1, 17, 21.0, bench=(6,)))]),
    # Traded in Week 7: 96 starter points for Abel, 165 for Jory, so Jory gets the credit
    (2020, "Tarn Whitlow", "WR", "SEA", 248.0, 1, [
        ("abel-trice", _log(1, 6, 16.0)),
        ("jory-paxton", _log(7, 17, 15.0)),
    ]),
    # 176 starter points each: Rue had him first
    (2020, "Ilan Cresswell", "QB", "KC", 330.0, 2, [
        ("rue-calloway", _log(1, 8, 22.0)),
        ("lyle-fenwick", _log(9, 16, 22.0)),
        ("odie-brask", _log(17, 17, 18.0)),
    ]),
    # 148.9 above replacement: just under the bar
    (2020, "Dov Penrose", "TE", "PHI", 354.0, 1, [("marlo-quist", _log(1, 17, 20.0))]),
    # Never started for anyone: not eligible, however many points
    (2020, "Kip Arlen", "RB", None, 300.0, 3, [("nell-ashgrove", _log(5, 17, 0.0, bench=tuple(range(5, 18))))]),
    (2018, "Eamon Stroud", "RB", "MIN", 330.6, 1, [("quinn-harrow", _log(1, 17, 19.0, bench=(3,)))]),
    # Exactly at the bar (132.4 + 150), on the example's former Owner
    (2018, "Harlo Bexley", "QB", "NO", 282.4, 1, [("wren-solano", _log(1, 17, 16.5))]),
]
# fmt: on


def _seasons() -> dict[int, dict]:
    out = {}
    for path in (EXAMPLES / "seasons").glob("*.json"):
        season = json.loads(path.read_text(encoding="utf-8"))
        out[season["year"]] = season
    return out


def derive() -> dict:
    seasons = _seasons()
    inductees = []
    for year, name, position, nfl_team, points, finish, logs in PLAYER_SEASONS:
        season = seasons[year]
        replacement = next(r["points"] for r in season["draft"]["replacement"] if r["position"] == position)
        par = round(max(points - replacement, 0.0), 2)  # points are 2-decimal; the pipeline's numeric is exact
        starts = [(sum(p for p in log.values() if p is not None), min(log), slug, log) for slug, log in logs]
        if par < PAR_BAR or all(p is None for *_, log in starts for p in log.values()):
            continue
        _, _, slug, _ = sorted(starts, key=lambda s: (-s[0], s[1]))[0]
        row = next(r for r in season["standings"] if r["owner"]["slug"] == slug)
        inductees.append(
            {
                "year": year,
                "scoringFormat": season["scoringFormat"]["label"],
                "name": name,
                "position": position,
                "nflTeam": nfl_team,
                "owner": row["owner"],
                "teamName": row["teamName"],
                "lanes": [{"lane": "dominant", "value": round(par, 2), "owner": row["owner"]}],
                "points": points,
                "positionalFinish": finish,
            }
        )
    inductees.sort(key=lambda i: (-i["year"], -i["lanes"][0]["value"], i["name"]))
    return {"inductees": inductees}


if __name__ == "__main__":
    out = EXAMPLES / "hall-of-fame.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
