"""Derive the Owner index and Owner documents from the other contract examples.

A reference implementation in plain Python, independent of the pipeline's SQL. It writes
contract/examples/owners.json and owners/<slug>.json, and test_site_contract.py uses it to
check those examples still agree with the Season and trophy-shelf examples.

    uv run python tests/owner_examples.py   # rewrite the examples
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def _load(relpath: str) -> dict:
    return json.loads((EXAMPLES / relpath).read_text(encoding="utf-8"))


def _seasons() -> dict[int, dict]:
    return {int(p.stem): _load(f"seasons/{p.name}") for p in sorted((EXAMPLES / "seasons").glob("*.json"))}


def _rec() -> dict:
    return {"wins": 0, "losses": 0, "ties": 0}


def _tally(record: dict, m: dict, side: str) -> None:
    """Add one played Matchup to `record` from `side`'s point of view."""
    if m["isTie"]:
        record["ties"] += 1
    elif m["winner"] == side:
        record["wins"] += 1
    else:
        record["losses"] += 1


def _played(matchups):
    """(matchup, home slug, away slug) for every non-bye Matchup."""
    for m in matchups:
        if not m["isBye"]:
            yield m, m["home"]["owner"]["slug"], m["away"]["owner"]["slug"]


def derive() -> tuple[dict, dict[str, dict]]:
    """(owner index, {slug: owner document})."""
    shelf = _load("trophy-shelf.json")["owners"]
    seasons = _seasons()
    refs = {e["owner"]["slug"]: e["owner"] for e in shelf}

    rows: dict[str, list[dict]] = {s: [] for s in refs}
    playoffs = {s: _rec() for s in refs}
    appearances: dict[str, list[int]] = {s: [] for s in refs}
    thirds: dict[str, list[int]] = {s: [] for s in refs}
    last_places: dict[str, list[int]] = {s: [] for s in refs}
    h2h: dict[str, dict[str, dict]] = {s: {} for s in refs}
    drafts: dict[str, list[dict]] = {s: [] for s in refs}

    def meeting(a: str, b: str) -> dict:
        return h2h[a].setdefault(b, {"regularSeason": _rec(), "playoffs": _rec()})

    for year, doc in seasons.items():
        podium = {p["owner"]["slug"]: p["place"] for p in doc["podium"]}
        last = doc["lastPlace"]["owner"]["slug"]
        for p in doc["podium"]:
            if p["place"] == 3:
                thirds[p["owner"]["slug"]].append(year)
        last_places[last].append(year)
        for r in doc["standings"]:
            slug = r["owner"]["slug"]
            rows[slug].append(
                {
                    "year": year,
                    "teamName": r["teamName"],
                    "record": r["record"],
                    "pointsFor": r["pointsFor"],
                    "pointsAgainst": r["pointsAgainst"],
                    "playoffSeed": r["playoffSeed"],
                    "finalRank": r["rank"],
                    "podiumPlace": podium.get(slug),
                    "isLastPlace": slug == last,
                }
            )
        # Draft: each Owner's Picks that Season, in pick order, with their Draft slot
        for o in doc["draft"]["order"]:
            slug = o["owner"]["slug"]
            picks = [
                {k: p[k] for k in ("overall", "round", "roundPick", "player")}
                for p in doc["draft"]["picks"]
                if p["owner"]["slug"] == slug
            ]
            drafts[slug].append({"year": year, "teamName": o["teamName"], "slot": o["slot"], "picks": picks})
        # Playoff appearance: any spot in the winners' bracket, a bye included
        bracket_games = [m for r in doc["bracket"]["rounds"] for m in r["matchups"]]
        in_bracket = {s["owner"]["slug"] for m in bracket_games for s in (m["home"], m["away"]) if s}
        for slug in in_bracket:
            appearances[slug].append(year)
        # Playoff record: winners'-bracket games played (the Third-place game is not a round)
        for rnd in doc["bracket"]["rounds"]:
            for m, home, away in _played(rnd["matchups"]):
                _tally(playoffs[home], m, "home")
                _tally(playoffs[away], m, "away")
                _tally(meeting(home, away)["playoffs"], m, "home")
                _tally(meeting(away, home)["playoffs"], m, "away")
        # Regular season: every Matchup period before the first playoff round
        first_playoff = min(r["matchupPeriod"] for r in doc["bracket"]["rounds"])
        for period in doc["weeklyResults"]:
            if period["matchupPeriod"] >= first_playoff:
                continue
            for m, home, away in _played(period["matchups"]):
                _tally(meeting(home, away)["regularSeason"], m, "home")
                _tally(meeting(away, home)["regularSeason"], m, "away")

    index, owners = [], {}
    for e in shelf:
        slug = e["owner"]["slug"]
        mine = sorted(rows[slug], key=lambda r: r["year"], reverse=True)
        regular = {k: sum(r["record"][k] for r in mine) for k in ("wins", "losses", "ties")}
        games = sum(regular.values())
        head = {"owner": e["owner"], "currentTeamName": e["currentTeamName"], "firstSeason": e["firstSeason"],
                "lastSeason": e["lastSeason"], "isFormer": e["isFormer"]}  # fmt: skip
        index.append({**head, "titles": e["titles"], "runnerUps": e["runnerUps"], "regularSeason": regular})
        opponents = []
        for opp, m in h2h[slug].items():
            meetings = sum(m["regularSeason"].values()) + sum(m["playoffs"].values())
            opponents.append({"opponent": refs[opp], **m, "meetings": meetings})
        opponents.sort(key=lambda o: (-o["meetings"], o["opponent"]["name"]))
        owners[slug] = {
            **head,
            "trophies": {"titles": e["titles"], "runnerUps": e["runnerUps"], "thirds": sorted(thirds[slug])},
            "career": {
                "regularSeason": regular,
                "playoffs": playoffs[slug],
                "avgPointsFor": round(sum(r["pointsFor"] for r in mine) / games, 2),
                "avgPointsAgainst": round(sum(r["pointsAgainst"] for r in mine) / games, 2),
                "playoffAppearances": sorted(appearances[slug]),
                "lastPlaces": sorted(last_places[slug]),
            },
            "seasons": mine,
            "headToHead": opponents,
            "draft": sorted(drafts[slug], key=lambda d: d["year"], reverse=True),
        }
    return {"owners": index}, owners


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    index, owners = derive()
    _write(EXAMPLES / "owners.json", index)
    for slug, doc in owners.items():
        _write(EXAMPLES / "owners" / f"{slug}.json", doc)
    print(f"wrote owners.json and {len(owners)} Owner documents")
