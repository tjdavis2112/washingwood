"""Derive the Transactions example (contract/examples/transactions.json): invented trades, scored.

A reference implementation in plain Python, independent of the pipeline's SQL. The trades below are
invented (ADR-0007); Owners and team names come from the Season examples so links resolve. Each
received Player has a Week-by-Week log for the receiving Owner: points as a starter, or None for a Week
on the bench. The rules applied here are the ones the pipeline follows:

- a side scores its received Players' starter points from the trade's Week to the end of the Season,
  playoff Weeks included, but each Player's Stint ends when they next leave that Owner;
- Margin = winning total minus losing total; equal totals are a tie with no winner;
- sides: winner first, a tie by Owner name; Players: most points first, then name;
- trades: newest Season, then newest Week, then the first side's Owner name.

test_site_contract.py checks the example still equals derive().

    uv run python tests/transactions_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"
LAST_WEEK = {2018: 17, 2020: 17}


def _log(first: int, last: int, points: float, *, bench: tuple[int, ...] = ()) -> dict[int, float | None]:
    """A steady weekly log: `points` each Week from `first` to `last`, None on the bench Weeks."""
    return {w: None if w in bench else points for w in range(first, last + 1)}


# (year, week, [(owner slug, [(name, position, NFL team, weekly log)]), ...two sides])
TRADES = [
    (2018, 4, [
        ("quinn-harrow", [("Corin Vale", "WR", "SEA", _log(4, 17, 12.5, bench=(9,)))]),
        ("abel-trice", [("Mott Ellery", "RB", "DEN", _log(4, 17, 6.0)),
                        ("Pim Arlo", "TE", "NO", _log(4, 17, 3.25, bench=(4, 5, 6)))]),
    ]),
    (2018, 11, [
        ("rue-calloway", [("Hollis Brandt", "QB", "KC", _log(11, 17, 21.0))]),
        ("pell-vantor", [("Tav Quill", "QB", "BAL", _log(11, 17, 15.5))]),
    ]),
    # Week 1, before the first roster snapshot: diffed against the draft roster
    (2020, 1, [
        ("ines-dorrow", [("Sable Wynn", "RB", "ATL", _log(1, 17, 9.0))]),
        ("cass-imber", [("Gage Ridley", "WR", None, _log(1, 17, 9.0, bench=(1,)))]),
    ]),
    # Nell receives Jem Corrow, then trades Jem on to Odie in Week 9: Nell's Stint is Weeks 3-8
    (2020, 3, [
        ("nell-ashgrove", [("Jem Corrow", "WR", "LV", _log(3, 17, 14.0))]),
        ("marlo-quist", [("Fenn Hale", "K", "CHI", _log(3, 17, 8.0))]),
    ]),
    (2020, 9, [
        ("odie-brask", [("Jem Corrow", "WR", "LV", _log(9, 17, 14.0))]),
        ("nell-ashgrove", [("Rook Tanner", "D/ST", "PIT", _log(9, 17, 7.0))]),
    ]),
    # A tie: equal totals
    (2020, 9, [
        ("jory-paxton", [("Lark Denholm", "TE", "MIA", _log(9, 17, 10.0))]),
        ("abel-trice", [("Bram Okafor", "RB", "TEN", _log(9, 17, 10.0))]),
    ]),
]  # fmt: skip


def _teams() -> dict[tuple[int, str], dict]:
    out = {}
    for path in (EXAMPLES / "seasons").glob("*.json"):
        season = json.loads(path.read_text(encoding="utf-8"))
        for row in season["standings"]:
            out[season["year"], row["owner"]["slug"]] = {
                "owner": row["owner"],
                "teamName": row["teamName"],
                "scoringFormat": season["scoringFormat"]["label"],
            }
    return out


def _left_week(year: int, week: int, name: str, slug: str) -> int:
    """The first later Week this Owner trades the Player away, else the Week after the Season ends."""
    later = [w for y, w, sides in TRADES if y == year and w > week
             for receiver, players in sides if receiver != slug
             for p in players if p[0] == name and any(s == slug for s, _ in sides)]  # fmt: skip
    return min(later, default=LAST_WEEK[year] + 1)


def _side(year: int, week: int, slug: str, players: list, teams) -> dict:
    scored = []
    for name, position, nfl_team, log in players:
        stint = [pts for w, pts in log.items() if week <= w < _left_week(year, week, name, slug) and pts is not None]
        scored.append({"name": name, "position": position, "nflTeam": nfl_team, "points": round(sum(stint), 2),
                       "weeksStarted": len(stint)})  # fmt: skip
    scored.sort(key=lambda p: (-p["points"], p["name"]))
    team = teams[year, slug]
    return {"owner": team["owner"], "teamName": team["teamName"], "total": round(sum(p["points"] for p in scored), 2),
            "players": scored}  # fmt: skip


def derive() -> dict:
    teams = _teams()
    trades = []
    for year, week, sides in TRADES:
        a, b = (_side(year, week, slug, players, teams) for slug, players in sides)
        a["outcome"] = "won" if a["total"] > b["total"] else "lost" if a["total"] < b["total"] else "tied"
        b["outcome"] = {"won": "lost", "lost": "won", "tied": "tied"}[a["outcome"]]
        pair = sorted([a, b], key=lambda s: (-s["total"], s["owner"]["name"]))
        trades.append({
            "year": year,
            "week": week,
            "scoringFormat": teams[year, sides[0][0]]["scoringFormat"],
            "margin": round(abs(a["total"] - b["total"]), 2),
            "sides": [{k: s[k] for k in ("owner", "teamName", "outcome", "total", "players")} for s in pair],
        })  # fmt: skip
    trades.sort(key=lambda t: (-t["year"], -t["week"], t["sides"][0]["owner"]["name"]))
    return {"trades": trades}


if __name__ == "__main__":
    out = EXAMPLES / "transactions.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
