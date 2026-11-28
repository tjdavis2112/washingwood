"""The Hall of Fame (GLOSSARY): Player seasons that clear a fixed Induction bar (ADR-0009).

`hall_of_fame_document()` builds hall-of-fame.json for `washingwood.build`. The calibration report prints,
per Season and lane, how many Player seasons clear a range of candidate bars, then the total Inductees per
Season at the current bars, so the bars can be set against the real Archive. It prints counts only, never a
Player or Owner name, so its output is safe to paste into an issue or PR:

    uv run python -m washingwood.hall_of_fame --report --archive ../washingwood-archive/<league> \
        --owners ../washingwood-archive/owners.yaml

The Postgres DSN comes from --pg or WASHINGWOOD_PG. It is never printed (it may hold a password).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import Connection

from washingwood.owners import slugify

# Induction bars (ADR-0009): fixed values, never ranks. A Player season clears a lane at value >= its bar.
# Calibrated against the real Archive in #74 and recorded in ADR-0009: changing one needs a new ADR.
PAR_BAR = 225.0  # Dominant: Points above replacement
POE_BAR = 150.0  # Overachiever: a Pick's Points over expected
PICKUP_BAR = 100.0  # Waiver legend: a Pickup's Value added over its Stint

# Candidate bars the calibration report counts against, per lane
PAR_CANDIDATES = (150, 175, 200, 210, 220, 230, 240, 250, 275, 300)
POE_CANDIDATES = (100, 125, 140, 150, 160, 170, 175, 200, 250)
PICKUP_CANDIDATES = (50, 60, 70, 75, 80, 90, 100, 125, 150)

# The lanes in credit order (ADR-0009): an Inductee is credited to the Owner of the first lane it cleared.
# (lane, report title, view, value column)
LANES = (
    ("dominant", "Dominant", "stats.dominant_seasons", "points_above_replacement"),
    ("overachiever", "Overachiever", "stats.overachiever_seasons", "points_over_expected"),
    ("waiver_legend", "Waiver legend", "stats.waiver_legend_seasons", "value_added"),
)

# What each lane's report table counts, its candidate bars and its constant's name
_REPORT = {
    "dominant": ("Player seasons with Points above replacement", PAR_CANDIDATES, "PAR_BAR"),
    "overachiever": ("Picks with Points over expected", POE_CANDIDATES, "POE_BAR"),
    "waiver_legend": ("Player seasons whose best Pickup's Value added is", PICKUP_CANDIDATES, "PICKUP_BAR"),
}


def _bars(trying: dict[str, float] | None = None) -> dict[str, float]:
    """Each lane's current bar, read at call time, with any the report is trying instead."""
    return {"dominant": PAR_BAR, "overachiever": POE_BAR, "waiver_legend": PICKUP_BAR, **(trying or {})}


def _lane_value(lane: str, value: Decimal) -> float | int:
    """Points over expected is whole points; the other two are rounded to 2 decimals."""
    return int(value) if lane == "overachiever" else round(float(value), 2)


def inductees(conn: Connection, trying: dict[str, float] | None = None) -> list[dict]:
    """Every Inductee: one per Player season that clears at least one bar, carrying every lane it cleared (in
    credit order, each with its value and Owner ref) and credited to its first lane's Owner. Newest Season
    first, then highest Points above replacement, then Player name. `trying` swaps in other bars (the report)."""
    bars = _bars(trying)
    cleared = " UNION ".join(
        f"SELECT season_id, player_id FROM {view} WHERE {col} >= %({lane})s" for lane, _, view, col in LANES
    )
    lane_cols = ", ".join(f"{lane}.franchise_id, {lane}.{col}" for lane, _, _, col in LANES)
    lane_joins = "\n".join(
        f"LEFT JOIN {view} {lane} ON {lane}.season_id = k.season_id AND {lane}.player_id = k.player_id"
        f" AND {lane}.{col} >= %({lane})s"
        for lane, _, view, col in LANES
    )
    rows = conn.execute(
        f"""WITH k AS ({cleared})
            SELECT s.year, s.scoring_label, p.full_name, ps.position, ps.nfl_team, ps.season_points,
                   psf.positional_finish, {lane_cols}
            FROM k
            JOIN core.seasons s                      ON s.season_id = k.season_id
            JOIN core.players p                      ON p.player_id = k.player_id
            JOIN core.player_seasons ps              ON ps.season_id = k.season_id AND ps.player_id = k.player_id
            LEFT JOIN stats.player_season_finish psf ON psf.season_id = k.season_id AND psf.player_id = k.player_id
            LEFT JOIN stats.points_above_replacement par
                   ON par.season_id = k.season_id AND par.player_id = k.player_id
            {lane_joins}
            ORDER BY s.year DESC, par.points_above_replacement DESC NULLS LAST, p.full_name""",
        {lane: Decimal(str(bar)) for lane, bar in bars.items()},
    ).fetchall()
    franchises = {
        fid: ({"slug": slugify(owner), "name": owner}, team)
        for fid, owner, team in conn.execute(
            """SELECT f.franchise_id, fo.display_name, f.team_name
               FROM core.franchises f JOIN stats.franchise_owner fo ON fo.franchise_id = f.franchise_id"""
        )
    }
    out = []
    for year, label, name, position, nfl_team, points, finish, *by_lane in rows:
        cleared_lanes = [
            (lane, fid, value)
            for (lane, *_), fid, value in zip(LANES, by_lane[::2], by_lane[1::2], strict=True)
            if fid is not None
        ]
        ref, team = franchises[cleared_lanes[0][1]]
        out.append(
            {
                "year": year,
                "scoringFormat": label,
                "name": name,
                "position": position,
                "nflTeam": nfl_team,
                "owner": ref,
                "teamName": team,
                "lanes": [
                    {"lane": lane, "value": _lane_value(lane, value), "owner": franchises[fid][0]}
                    for lane, fid, value in cleared_lanes
                ],
                "points": None if points is None else float(points),  # null: no Season points in the Archive
                "positionalFinish": finish,
            }
        )
    return out


def hall_of_fame_document(conn: Connection) -> dict:
    """hall-of-fame.json. Season and Owner pages filter this document at site build time (by `year`, or by
    the credited Owner's slug) rather than carrying their own copy."""
    return {"inductees": inductees(conn)}


def _lane_values(conn: Connection, view: str, col: str) -> dict[int, list[float]]:
    """Every Season (oldest first), with each of its Player seasons' values in one lane."""
    return {
        year: [float(v) for v in values]
        for year, values in conn.execute(
            f"""SELECT s.year, coalesce(array_agg(x.{col}) FILTER (WHERE x.player_id IS NOT NULL), '{{}}')
                FROM core.seasons s
                LEFT JOIN {view} x ON x.season_id = s.season_id
                GROUP BY s.year ORDER BY s.year"""
        )
    }


def report(conn: Connection, trying: dict[str, float] | None = None) -> str:
    """Per Season: for each lane, how many Player seasons clear each candidate bar and the current one; then
    the Inductees per Season at the current bars, or at the bars in `trying`. Counts only."""
    bars = _bars(trying)
    values = {lane: _lane_values(conn, view, col) for lane, _, view, col in LANES}
    per_season = Counter(i["year"] for i in inductees(conn, trying))
    years = list(values["dominant"])
    width = 6
    lines = ["Hall of Fame calibration report: counts only, no Player or Owner names."]
    if trying:
        names = {lane: name for lane, (_, _, name) in _REPORT.items()}
        lines.append(
            "Bars below are the ones being tried, not the constants: trying "
            + ", ".join(f"{names[lane]} {bars[lane]:g}" for lane, *_ in LANES)
            + "."
        )
    for lane, title, _, _ in LANES:
        what, candidates, name = _REPORT[lane]
        bar = bars[lane]
        lines += [
            "",
            f"{title}: {what} at or above each bar.",
            f"The last column is {'the' if trying else 'the current'} {name} ({bar:g}).",
            "Season" + "".join(f"{'>=' + str(b):>{width}}" for b in candidates) + f"{'bar ' + f'{bar:g}':>10}",
        ]
        for year, vals in values[lane].items():
            counts = "".join(f"{sum(v >= b for v in vals):>{width}}" for b in candidates)
            lines.append(f"{year:<6}{counts}{sum(v >= bar for v in vals):>10}")
    lines += [
        "",
        f"Inductees per Season at {'these' if trying else 'the current'} bars"
        " (a Player season clearing several lanes counts once):",
        f"{'Season':<8}{'Dominant':>10}{'Overachiever':>14}{'Waiver legend':>15}{'Total':>7}",
    ]
    for year in years:
        d, o, w = (sum(v >= bars[lane] for v in values[lane][year]) for lane, *_ in LANES)
        lines.append(f"{year:<8}{d:>10}{o:>14}{w:>15}{per_season[year]:>7}")
    total = sum(per_season.values())
    lines += ["", f"Inductees at {'these' if trying else 'the current'} bars: {total} across {len(years)} Season(s)."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from washingwood.build import FAILURES, load_archive  # build imports this module

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--report", action="store_true", required=True, help="print the calibration report")
    p.add_argument("--archive", required=True, type=Path, help="archive/<league> folder holding one folder per Season")
    p.add_argument("--owners", required=True, type=Path, help="owners.yaml (private)")
    p.add_argument("--pg", default=os.environ.get("WASHINGWOOD_PG"), help="Postgres DSN; default $WASHINGWOOD_PG")
    p.add_argument("--par", type=float, help="try this Dominant bar instead of PAR_BAR (report only)")
    p.add_argument("--poe", type=float, help="try this Overachiever bar instead of POE_BAR (report only)")
    p.add_argument("--pickup", type=float, help="try this Waiver legend bar instead of PICKUP_BAR (report only)")
    args = p.parse_args(argv)
    flags = {"dominant": args.par, "overachiever": args.poe, "waiver_legend": args.pickup}
    trying = {lane: bar for lane, bar in flags.items() if bar is not None}
    if not args.pg:
        p.error("no Postgres DSN: pass --pg or set WASHINGWOOD_PG")
    try:
        with psycopg.connect(args.pg) as conn:
            load_archive(conn, args.archive, args.owners)
            print(report(conn, trying))
    except FAILURES as e:
        print(f"report failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
