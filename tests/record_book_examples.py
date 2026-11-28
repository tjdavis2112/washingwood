"""Derive the Record Book example (contract/examples/record-book.json) from the Season and Box score
examples: Week records, Season records (Luck index included), the All-time table, Streaks, Last place
history and the per-Owner tally.

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


def all_play_pct(box: dict | None) -> dict[str, Decimal]:
    """Owner slug -> all-play win % (GLOSSARY) over the Season's regular-season Weeks, from the Box scores'
    starter points: each Week, 1 per other Franchise outscored and 1/2 per tie, divided by the number of
    other Franchises that Week, averaged over the Weeks. Empty without Box scores."""
    weeks: dict[int, dict[str, Decimal]] = {}
    for m in (box or {"matchups": []})["matchups"]:
        if m["kind"] != "regular":
            continue
        for side in (m["home"], m.get("away")):
            if not side:
                continue
            for w in side["weeks"]:
                starters = sum((Decimal(str(e["points"] or 0)) for e in w["starters"]), Decimal(0))
                weeks.setdefault(w["week"], {})[side["owner"]["slug"]] = starters
    shares: dict[str, list[Decimal]] = {}
    for scores in weeks.values():
        others = len(scores) - 1
        for slug, pts in scores.items():
            won = sum((Decimal(1) if pts > o else Decimal("0.5") if pts == o else Decimal(0))
                      for other, o in scores.items() if other != slug)  # fmt: skip
            shares.setdefault(slug, []).append(won / others)
    return {slug: sum(v, Decimal(0)) / len(v) for slug, v in shares.items()}


def season_rows(season: dict, box: dict | None = None) -> list[dict]:
    """Every Franchise-Season in a Season, from its standings, with Bench points from its Box scores."""
    bench = season_bench(box)
    pct = all_play_pct(box)
    rows = []
    for s in season["standings"]:
        r = {"year": season["year"], "owner": s["owner"], "teamName": s["teamName"], "record": s["record"]}
        r |= _rates(s["record"], s["pointsFor"])
        r["pointsAgainst"] = s["pointsAgainst"]
        r["pointsAgainstPerGame"] = _round(Decimal(str(s["pointsAgainst"])) / r["games"], 2)
        slug = s["owner"]["slug"]
        r["benchPoints"] = float(bench[slug]) if slug in bench else None
        # Luck index: actual wins - Expected wins (all-play win % x games)
        expected = pct[slug] * r["games"] if slug in pct else None
        r["expectedWins"] = None if expected is None else _round(expected, 2)
        r["luck"] = None if expected is None else _round(s["record"]["wins"] - expected, 1)
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
    ("luckiest", "luck", True),
    ("unluckiest", "luck", False),
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
            {"owner": r["owner"], "seasons": 0, "w": 0, "l": 0, "t": 0, "pf": Decimal(0), "bench": None, "luck": None},
        )
        e["seasons"] += 1
        e["w"] += r["record"]["wins"]
        e["l"] += r["record"]["losses"]
        e["t"] += r["record"]["ties"]
        e["pf"] += Decimal(str(r["pointsFor"]))
        if r["benchPoints"] is not None:
            e["bench"] = (e["bench"] or Decimal(0)) + Decimal(str(r["benchPoints"]))
        if r["luck"] is not None:
            e["luck"] = (e["luck"] or Decimal(0)) + Decimal(str(r["luck"]))
    out = []
    for slug, e in by_owner.items():
        record = {"wins": e["w"], "losses": e["l"], "ties": e["t"]}
        row = {"owner": e["owner"], "seasons": e["seasons"], "record": record}
        row |= _rates(record, float(e["pf"]))
        row["benchPoints"] = None if e["bench"] is None else float(e["bench"])
        row["luck"] = None if e["luck"] is None else float(e["luck"])
        row["lastPlaces"] = sum(1 for lp in last_places if lp["owner"]["slug"] == slug)
        out.append(row)
    return sorted(out, key=lambda r: (-r["record"]["wins"], r["owner"]["name"]))


def regular_games(season: dict) -> list[tuple[str, dict, int, str]]:
    """Every regular-season game in a Season, in Matchup-period order: (Owner slug, Owner ref, Week, W/L/T),
    one per side. Regular-season periods are the weekly results before the first bracket round; byes aren't
    games."""
    first_round = season["bracket"]["rounds"][0]["matchupPeriod"]
    out = []
    for period in sorted(season["weeklyResults"], key=lambda p: p["matchupPeriod"]):
        if period["matchupPeriod"] >= first_round:
            continue
        for m in period["matchups"]:
            if m["isBye"]:
                continue
            for who in ("home", "away"):
                result = "T" if m["isTie"] else "W" if m["winner"] == who else "L"
                out.append((m[who]["owner"]["slug"], m[who]["owner"], period["weeks"][0], result))
    return out


def streaks(seasons: list[dict]) -> tuple[dict, dict[str, dict]]:
    """Streaks (GLOSSARY) over every Season, oldest first: runs of regular-season wins or losses per Owner;
    a sat-out Season doesn't break one, a tie ends it. Active: runs through the Owner's last game, played in
    the latest Season. Returns the top-10 lists and each Owner's longest of each kind."""
    latest = max(s["year"] for s in seasons)
    games: dict[str, list] = {}
    for season in sorted(seasons, key=lambda s: s["year"]):
        for slug, ref, week, result in regular_games(season):
            games.setdefault(slug, []).append((season["year"], ref, week, result))
    runs: dict[str, list[dict]] = {"W": [], "L": []}
    longest = {}
    for slug, played in games.items():
        kind, run = None, None
        for year, ref, week, result in played:
            if result == "T":
                kind, run = None, None
            elif result == kind:
                run["length"] += 1
                run["end"] = {"year": year, "week": week}
            else:
                kind = result
                run = {
                    "owner": ref,
                    "length": 1,
                    "start": {"year": year, "week": week},
                    "end": {"year": year, "week": week},
                    "active": False,
                }
                runs[kind].append(run)
        if run is not None and played[-1][0] == latest:
            run["active"] = True
        longest[slug] = {
            "longestWinStreak": max((r["length"] for r in runs["W"] if r["owner"]["slug"] == slug), default=0),
            "longestLossStreak": max((r["length"] for r in runs["L"] if r["owner"]["slug"] == slug), default=0),
        }

    def top(kind):
        return sorted(
            runs[kind], key=lambda r: (-r["length"], r["start"]["year"], r["start"]["week"], r["owner"]["name"])
        )[:10]

    return {"wins": top("W"), "losses": top("L")}, longest


def _seasons() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / "seasons").glob("*.json"), reverse=True)
    ]


def _box_scores(year: int) -> dict | None:
    path = EXAMPLES / "box-scores" / f"{year}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def derive() -> dict:
    """record-book.json: Week and Season records, the All-time table, Streaks, Last place per Season (newest
    first) and the tally."""
    seasons = _seasons()
    boxes = {s["year"]: _box_scores(s["year"]) for s in seasons}
    rows = [r for s in seasons for r in season_rows(s, boxes[s["year"]])]
    last = [last_place_row(s) for s in seasons]
    streak_lists, longest = streaks(seasons)
    return {
        "week": week_records([r for s in seasons for r in week_rows(s, boxes[s["year"]])]),
        "season": season_records(rows),
        "allTime": [r | longest[r["owner"]["slug"]] for r in all_time(rows, last)],
        "streaks": streak_lists,
        "lastPlace": {"seasons": last, "tally": tally(last)},
    }


if __name__ == "__main__":
    out = EXAMPLES / "record-book.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
