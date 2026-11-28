"""Derive the Hall of Fame example (contract/examples/hall-of-fame.json): invented Player seasons, inducted.

A reference implementation in plain Python, independent of the pipeline's SQL. The Player seasons below are
invented (ADR-0007); Owners and team names come from the Season examples so links resolve. Each Player has
his Season points, Positional finish and, per Owner who rostered him, a Week-by-Week log: points as a
starter, or None for a Week on the bench. A drafted Player also has his Pick (the drafting Owner and the
Round's expectation), and a Player picked up has each Pickup (the acquiring Owner and its Value added over
the Stint). The rules applied here are the ones the pipeline follows (ADR-0009, GLOSSARY: Induction bar):

- Points above replacement = Season points minus the position's Replacement points that Season (the Season
  example's draft.replacement), never below 0;
- Dominant: Points above replacement at or above PAR_BAR (washingwood.hall_of_fame), credited to the Owner
  he scored the most starter points for; a tie goes to the earlier acquisition (the Owner whose log starts
  first); a Player who never started for anyone is not eligible;
- Overachiever: Points over expected (Points above replacement minus the Round's expectation, rounded to
  whole points) at or above POE_BAR, credited to the drafting Owner;
- Waiver legend: the best Pickup's Value added at or above PICKUP_BAR, credited to that Pickup's Owner;
- one Inductee per Player season with every lane it cleared, in credit order (Dominant, Overachiever, Waiver
  legend), credited to the first lane's Owner;
- a Player with no Season points has no Points above replacement (so only the Waiver legend lane), and null
  points and Positional finish;
- inductees: newest Season first, then highest Points above replacement (none last), then Player name.

Moments (the card back) are all for the credited Owner, read from his weekly log and the Season example's
weeklyResults, bracket and standings:

- best Week: his highest starter score in a Counted Matchup (a regular-season Week, or a single-Week
  championship-bracket Matchup his Owner played); a tie goes to the earlier Week. None if he never started;
- playoff points: his starter points over every Week of the championship-bracket Matchups his Owner played
  (byes aren't played; both Weeks of a two-Week round count), None if the Owner played none;
- championship points: the same for the championship game, None if his Owner wasn't in it;
- finish: the Owner's final rank and seed, and whether he made the playoffs (appears in the bracket);
- Weeks started: every Week in the log he started.

The Owner's note comes from NOTES, null for the rest.

test_site_contract.py checks the example still equals derive().

    uv run python tests/hall_of_fame_examples.py   # rewrite the example
"""

from __future__ import annotations

import json
from pathlib import Path

from washingwood.hall_of_fame import PAR_BAR, PICKUP_BAR, POE_BAR

EXAMPLES = Path(__file__).resolve().parents[1] / "contract" / "examples"


def _log(
    first: int, last: int, points: float, *, bench: tuple[int, ...] = (), peaks: dict[int, float] | None = None
) -> dict[int, float | None]:
    """A steady weekly log: `points` each Week from `first` to `last`, None on the bench Weeks, `peaks` on top."""
    return {w: None if w in bench else (peaks or {}).get(w, points) for w in range(first, last + 1)}


# (year, name, position, NFL team, Season points, Positional finish, [(owner slug, weekly log), ...],
#  Pick as (owner slug, Round expectation) or None, [(owner slug, Value added), ...] Pickups)
# fmt: off
PLAYER_SEASONS = [
    # Dominant and Overachiever, both for Cass. Best Week 11 (41.5); 33.25 in his one playoff game, a semifinal loss
    (2020, "Bodhi Lanark", "RB", "DAL", 362.4, 1,
     [("cass-imber", _log(1, 17, 21.0, bench=(6,), peaks={11: 41.5, 16: 33.25}))],
     ("cass-imber", 100.0), []),
    # Drafted by Abel, traded in Week 7: 96 starter points for Abel, 165 for Jory, so Jory gets the Dominant
    # credit and the card, and Abel keeps the Overachiever lane
    (2020, "Tarn Whitlow", "WR", "SEA", 317.0, 1, [
        ("abel-trice", _log(1, 6, 16.0)),
        ("jory-paxton", _log(7, 17, 15.0)),
    ], ("abel-trice", 40.0), []),
    # 176 starter points each: Rue had him first
    (2020, "Ilan Cresswell", "QB", "KC", 330.0, 2, [
        ("rue-calloway", _log(1, 8, 22.0)),
        ("lyle-fenwick", _log(9, 16, 22.0)),
        ("odie-brask", _log(17, 17, 18.0)),
    ], None, []),
    # 223.9 above replacement: just under the Dominant bar
    (2020, "Dov Penrose", "TE", "PHI", 429.0, 1, [("marlo-quist", _log(1, 17, 20.0))], None, []),
    # Never started for anyone, so not Dominant, but exactly 150 over expected: an Overachiever for Nell
    (2020, "Kip Arlen", "RB", None, 340.0, 3, [("nell-ashgrove", _log(5, 17, 0.0, bench=tuple(range(5, 18))))],
     ("nell-ashgrove", 84.8), []),
    # 149 over expected: just under the Overachiever bar
    (2020, "Sully Brannock", "RB", "ATL", 305.2, 6, [("pell-vantor", _log(1, 17, 13.0))],
     ("pell-vantor", 51.0), []),
    # Picked up by Odie, dropped, then picked up by Marlo: the best Pickup (Marlo's) counts
    (2020, "Wade Fennick", "WR", "LAR", 180.0, 4, [
        ("odie-brask", _log(3, 6, 9.0)),
        ("marlo-quist", _log(9, 17, 14.0)),
    ], None, [("odie-brask", 12.4), ("marlo-quist", 112.5)]),
    # 99.99 Value added: just under the Waiver legend bar
    (2020, "Merritt Vale", "WR", "CHI", 120.0, 9, [("tamsin-oake", _log(4, 17, 8.0))],
     None, [("tamsin-oake", 99.99)]),
    (2018, "Eamon Stroud", "RB", "MIN", 330.6, 1, [("quinn-harrow", _log(1, 17, 19.0, bench=(3,)))], None, []),
    # Exactly at the Dominant bar (132.4 + 225), on the example's former Owner
    (2018, "Harlo Bexley", "QB", "NO", 357.4, 1, [("wren-solano", _log(1, 17, 16.5))], None, []),
    # Exactly at the Waiver legend bar, with no Season points in the Archive: null points and finish, sorted last
    (2018, "Ozzie Calder", "RB", "TEN", None, None, [("pell-vantor", _log(4, 17, 10.0))],
     None, [("pell-vantor", 100.0)]),
    # Drafted by Lyle (160 over expected), dropped, picked up by Tamsin: credited to Lyle, the Overachiever
    # Owner, with Tamsin's Waiver legend lane on the card too
    (2018, "Ruel Haskett", "WR", "DEN", 278.6, 5, [
        ("lyle-fenwick", _log(1, 3, 6.0)),
        ("tamsin-oake", _log(5, 17, 11.0)),
    ], ("lyle-fenwick", 30.0), [("tamsin-oake", 118.4)]),
]
# fmt: on

# Owner's notes (invented), by (year, Player): the rest are null, "coming soon" on the card
NOTES = {
    (2020, "Tarn Whitlow"): "Traded for him in Week 7 and never looked back.",
    (2018, "Eamon Stroud"): "Two-week rounds, two weeks of him. Title.",
}


def _seasons() -> dict[int, dict]:
    out = {}
    for path in (EXAMPLES / "seasons").glob("*.json"):
        season = json.loads(path.read_text(encoding="utf-8"))
        out[season["year"]] = season
    return out


def _result(matchup: dict, slug: str) -> tuple[dict, str]:
    """(opponent Owner ref, win/loss/tie) for `slug` in a played Matchup."""
    side = "home" if matchup["home"]["owner"]["slug"] == slug else "away"
    other = matchup["away" if side == "home" else "home"]
    result = "tie" if matchup["isTie"] else "win" if matchup["winner"] == side else "loss"
    return other["owner"], result


def _moments(season: dict, slug: str, log: dict[int, float | None]) -> dict:
    def plays(m):
        return not m["isBye"] and slug in (
            m["home"]["owner"]["slug"],
            (m.get("away") or {}).get("owner", {}).get("slug"),
        )

    bracket = season["bracket"]["rounds"]
    playoff_periods = {r["matchupPeriod"] for r in bracket}
    # Counted Matchups his Owner played, by Week: regular-season Weeks and single-Week bracket rounds
    counted = {}
    for period in season["weeklyResults"]:
        if period["matchupPeriod"] in playoff_periods:
            continue
        (week,) = period["weeks"]
        counted[week] = next(m for m in period["matchups"] if plays(m))
    played = [(r, next((m for m in r["matchups"] if plays(m)), None)) for r in bracket]
    played = [(r, m) for r, m in played if m is not None]
    for r, m in played:
        if len(r["weeks"]) == 1:
            counted[r["weeks"][0]] = m
    starts = [(w, p) for w, p in log.items() if p is not None and w in counted]
    best_week = None
    if starts:
        week, points = sorted(starts, key=lambda s: (-s[1], s[0]))[0]
        opponent, result = _result(counted[week], slug)
        best_week = {"week": week, "points": points, "opponent": opponent, "result": result}

    def points_in(weeks):
        return round(sum(log.get(w) or 0.0 for w in weeks), 2)

    final = bracket[-1]  # the Championship round
    standing = next(r for r in season["standings"] if r["owner"]["slug"] == slug)
    in_bracket = any(slug in (m["home"]["owner"]["slug"], (m.get("away") or {}).get("owner", {}).get("slug"))
                     for r in bracket for m in r["matchups"])  # fmt: skip
    return {
        "bestWeek": best_week,
        "playoffPoints": points_in(w for r, _ in played for w in r["weeks"]) if played else None,
        "championshipPoints": points_in(final["weeks"]) if any(r is final for r, _ in played) else None,
        "finish": {"finalRank": standing["rank"], "playoffSeed": standing["playoffSeed"], "madePlayoffs": in_bracket},
        "weeksStarted": sum(p is not None for p in log.values()),
    }


def derive() -> dict:
    seasons = _seasons()
    rows = []
    for year, name, position, nfl_team, points, finish, logs, pick, pickups in PLAYER_SEASONS:
        season = seasons[year]
        replacement = next(r["points"] for r in season["draft"]["replacement"] if r["position"] == position)
        # points are 2-decimal; the pipeline's numeric is exact. No Season points: no Points above replacement
        par = None if points is None else round(max(points - replacement, 0.0), 2)
        cleared = []  # (lane, value, owner slug), in credit order
        started = any(p is not None for _, log in logs for p in log.values())
        if started and par is not None and par >= PAR_BAR:
            starts = [(sum(p for p in log.values() if p is not None), min(log), slug) for slug, log in logs]
            cleared.append(("dominant", par, sorted(starts, key=lambda s: (-s[0], s[1]))[0][2]))
        if pick is not None and par is not None:
            drafter, expected = pick
            poe = int(round(par - expected))
            if poe >= POE_BAR:
                cleared.append(("overachiever", poe, drafter))
        if pickups:
            slug, value = max(pickups, key=lambda p: p[1])  # the best; a tie keeps the earlier Pickup
            if value >= PICKUP_BAR:
                cleared.append(("waiver_legend", value, slug))
        if not cleared:
            continue
        standing = {r["owner"]["slug"]: r for r in season["standings"]}
        credited = standing[cleared[0][2]]
        inductee = {
            "year": year,
            "scoringFormat": season["scoringFormat"]["label"],
            "name": name,
            "position": position,
            "nflTeam": nfl_team,
            "owner": credited["owner"],
            "teamName": credited["teamName"],
            "lanes": [
                {"lane": lane, "value": value, "owner": standing[slug]["owner"]} for lane, value, slug in cleared
            ],
            "points": points,
            "positionalFinish": finish,
            "moments": _moments(season, cleared[0][2], dict(logs).get(cleared[0][2], {})),
            "ownerNote": NOTES.get((year, name)),
        }
        rows.append((-year, par is None, -(par or 0.0), name, inductee))
    return {"inductees": [i for *_, i in sorted(rows, key=lambda r: r[:4])]}


if __name__ == "__main__":
    out = EXAMPLES / "hall-of-fame.json"
    out.write_text(json.dumps(derive(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}")
