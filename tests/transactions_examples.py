"""Derive the Transactions example (contract/examples/transactions.json): invented trades and Pickups, scored.

A reference implementation in plain Python, independent of the pipeline's SQL. The trades below are
invented (ADR-0007); Owners and team names come from the Season examples so links resolve. Each
received Player has a Week-by-Week log for the receiving Owner: points as a starter, or None for a Week
on the bench. The rules applied here are the ones the pipeline follows:

- a side scores its received Players' starter points from the trade's Week to the end of the Season,
  playoff Weeks included, but each Player's Stint ends when they next leave that Owner;
- Margin = winning total minus losing total; equal totals are a tie with no winner;
- sides: winner first, a tie by Owner name; Players: most points first, then name;
- trades: newest Season, then newest Week, then the first side's Owner name;
- Pickups score the same way: an added Player's log holds only the Weeks they were in that Owner's
  lineup, and a Stint ends at that Owner's next acquisition of the Player, so a re-add is a new Pickup;
- Best pickups: top 10 by points, ties by Season, then Week, then Owner name, then Player name; each
  Season also gets its own top 10 (seasonPickups, newest Season first), and each Owner a top 5;
- trade records: won, lost, tied and net points per Owner who traded, highest net points first.

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
    # 2018 has no trades, so its Season page shows the empty-Season line
    (2020, 4, [
        ("quinn-harrow", [("Corin Vale", "WR", "SEA", _log(4, 17, 12.5, bench=(9,)))]),
        ("abel-trice", [("Mott Ellery", "RB", "DEN", _log(4, 17, 6.0)),
                        ("Pim Arlo", "TE", "NO", _log(4, 17, 3.25, bench=(4, 5, 6)))]),
    ]),
    (2020, 11, [
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


# Pickups: (year, week added, Owner slug, name, position, NFL team, via, weekly log in that Owner's lineup)
PICKUPS = [
    (2018, 2, "lyle-fenwick", "Dov Kessling", "RB", "IND", "waiver", _log(2, 17, 11.0, bench=(2,))),
    (2018, 6, "wren-solano", "Ash Pelham", "WR", "GB", "free_agent", _log(6, 17, 9.5)),
    (2018, 9, "marlo-quist", "Kip Tolland", "TE", "NYG", "waiver", _log(9, 17, 6.0)),
    (2018, 12, "odie-brask", "Rey Hatcher", "D/ST", "CLE", "free_agent", _log(12, 17, 8.0)),
    (2018, 3, "tamsin-oake", "Ivo Brennick", "QB", None, "free_agent", _log(3, 4, 14.0)),
    # Dropped after Week 7 and re-added in Week 12: two Pickups, no Week counted twice
    (2020, 2, "pell-vantor", "Nico Strand", "WR", "DAL", "waiver", _log(2, 7, 12.0) | _log(12, 17, 12.0)),
    (2020, 12, "pell-vantor", "Nico Strand", "WR", "DAL", "waiver", _log(12, 17, 12.0)),
    (2020, 4, "jory-paxton", "Cal Mercer", "RB", "NE", "free_agent", _log(4, 17, 10.0)),
    (2020, 5, "rue-calloway", "Tobin Ashe", "K", "HOU", "waiver", _log(5, 17, 7.25)),
    (2020, 7, "quinn-harrow", "Juno Pratt", "TE", "ARI", "free_agent", _log(7, 17, 5.0, bench=(15, 16, 17))),
    # Equal points: the earlier Week ranks first, then the Owner name
    (2020, 10, "lyle-fenwick", "Wes Garland", "RB", "SF", "waiver", _log(10, 17, 9.0)),
    (2020, 10, "cass-imber", "Orrin Vey", "WR", "TB", "free_agent", _log(10, 17, 9.0)),
    (2020, 15, "tamsin-oake", "Hale Brook", "QB", "MIN", "free_agent", _log(15, 17, 3.0)),
]


def best_pickups(teams, season: int | None = None, owner: str | None = None, limit: int = 10) -> list[dict]:
    """The top Pickups of all time, of one Season, or of one Owner (by slug)."""
    rows = []
    for year, week, slug, name, position, nfl_team, via, log in PICKUPS:
        if (season is not None and year != season) or (owner is not None and slug != owner):
            continue
        # The Stint ends at this Owner's next acquisition of the Player (a re-add or a trade)
        later = [w for y, w, o, n, *_ in PICKUPS if (y, o, n) == (year, slug, name) and w > week]
        later += [w for y, w, sides in TRADES if y == year and w > week
                  for o, players in sides if o == slug and any(p[0] == name for p in players)]  # fmt: skip
        end = min(later, default=LAST_WEEK[year] + 1)
        stint = [pts for w, pts in log.items() if week <= w < end and pts is not None]
        team = teams[year, slug]
        rows.append({"name": name, "position": position, "nflTeam": nfl_team, "owner": team["owner"],
                     "teamName": team["teamName"], "year": year, "week": week, "via": via,
                     "points": round(sum(stint), 2), "weeksStarted": len(stint),
                     "scoringFormat": team["scoringFormat"]})  # fmt: skip
    rows.sort(key=lambda r: (-r["points"], r["year"], r["week"], r["owner"]["name"], r["name"]))
    return rows[:limit]


def trade_records(trades: list[dict]) -> list[dict]:
    """Per Owner who traded: won, lost, tied and net points (own side minus the other side, summed)."""
    out: dict[str, dict] = {}
    for t in trades:
        for side, other in (t["sides"], t["sides"][::-1]):
            r = out.setdefault(side["owner"]["slug"], {"owner": side["owner"], "trades": 0, "won": 0, "lost": 0,
                                                        "tied": 0, "netPoints": 0.0})  # fmt: skip
            r["trades"] += 1
            r[side["outcome"]] += 1
            r["netPoints"] = round(r["netPoints"] + side["total"] - other["total"], 2)
    return sorted(out.values(), key=lambda r: (-r["netPoints"], r["owner"]["name"]))


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
    years = sorted({year for year, _ in teams}, reverse=True)
    return {
        "trades": trades,
        "pickups": best_pickups(teams),
        "seasonPickups": [{"year": y, "pickups": best_pickups(teams, y)} for y in years],
        "tradeRecords": trade_records(trades),
        "ownerPickups": [
            {"owner": o, "pickups": best_pickups(teams, owner=o["slug"], limit=5)}
            for o in sorted({t["owner"]["slug"]: t["owner"] for t in teams.values()}.values(), key=lambda o: o["name"])
        ],
    }


if __name__ == "__main__":
    out = EXAMPLES / "transactions.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
