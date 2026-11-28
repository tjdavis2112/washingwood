"""The Hall of Fame (GLOSSARY): Player seasons that clear a fixed Induction bar (ADR-0009).

`hall_of_fame_document()` builds hall-of-fame.json for `washingwood.build`. The calibration report prints,
per Season, how many Player seasons clear a range of candidate bars, so the bars can be set against the
real Archive. It prints counts only, never a Player or Owner name, so its output is safe to paste into an
issue or PR:

    uv run python -m washingwood.hall_of_fame --report --archive ../washingwood-archive/<league> \
        --owners ../washingwood-archive/owners.yaml

The Postgres DSN comes from --pg or WASHINGWOOD_PG. It is never printed (it may hold a password).
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import Connection

from washingwood.owners import slugify

# Induction bars (ADR-0009): fixed values, never ranks. A Player season clears a lane at value >= its bar.
# Placeholder until calibrated against the real Archive in #74, then recorded in ADR-0009.
PAR_BAR = 150.0  # Dominant: Points above replacement

# Candidate bars the calibration report counts against
PAR_CANDIDATES = (50, 75, 100, 125, 150, 175, 200, 250, 300)


def hall_of_fame_document(conn: Connection) -> dict:
    """The Hall of Fame: every Inductee, newest Season first, then highest Points above replacement, then
    Player name. Each is credited to the Owner of the Franchise the Player scored the most starter points for
    (stats.dominant_seasons). Season and Owner pages filter this document at site build time (by `year`, or
    by the credited Owner's slug) rather than carrying their own copy."""
    rows = conn.execute(
        """SELECT s.year, s.scoring_label, p.full_name, d.position, ps.nfl_team, fo.display_name, f.team_name,
                  d.points_above_replacement, d.season_points, d.positional_finish
           FROM stats.dominant_seasons d
           JOIN core.seasons s           ON s.season_id = d.season_id
           JOIN core.players p           ON p.player_id = d.player_id
           JOIN core.player_seasons ps   ON ps.season_id = d.season_id AND ps.player_id = d.player_id
           JOIN core.franchises f        ON f.franchise_id = d.franchise_id
           JOIN stats.franchise_owner fo ON fo.franchise_id = d.franchise_id
           WHERE d.points_above_replacement >= %s
           ORDER BY s.year DESC, d.points_above_replacement DESC, p.full_name""",
        (Decimal(str(PAR_BAR)),),
    ).fetchall()
    inductees = []
    for year, label, name, position, nfl_team, owner, team, par, points, finish in rows:
        ref = {"slug": slugify(owner), "name": owner}
        inductees.append(
            {
                "year": year,
                "scoringFormat": label,
                "name": name,
                "position": position,
                "nflTeam": nfl_team,
                "owner": ref,
                "teamName": team,
                "lanes": [{"lane": "dominant", "value": round(float(par), 2), "owner": ref}],
                "points": float(points),
                "positionalFinish": finish,
            }
        )
    return {"inductees": inductees}


def report(conn: Connection) -> str:
    """Per Season, how many Player seasons clear each candidate bar and the current one. Counts only."""
    by_season = {
        year: [float(v) for v in values]
        for year, values in conn.execute(
            """SELECT s.year, coalesce(array_agg(d.points_above_replacement)
                                          FILTER (WHERE d.player_id IS NOT NULL), '{}')
               FROM core.seasons s
               LEFT JOIN stats.dominant_seasons d ON d.season_id = s.season_id
               GROUP BY s.year ORDER BY s.year"""
        )
    }
    width = 6
    header = "Season" + "".join(f"{'>=' + str(b):>{width}}" for b in PAR_CANDIDATES) + f"{'bar ' + f'{PAR_BAR:g}':>10}"
    lines = [
        "Hall of Fame calibration report: counts only, no Player or Owner names.",
        "",
        "Dominant: Player seasons with Points above replacement at or above each bar.",
        f"The last column is the current PAR_BAR ({PAR_BAR:g}): that Season's Dominant Inductees.",
        "",
        header,
    ]
    for year, values in by_season.items():
        counts = "".join(f"{sum(v >= b for v in values):>{width}}" for b in PAR_CANDIDATES)
        lines.append(f"{year:<6}{counts}{sum(v >= PAR_BAR for v in values):>10}")
    total = sum(sum(v >= PAR_BAR for v in values) for values in by_season.values())
    lines += ["", f"Inductees at the current bars: {total} across {len(by_season)} Season(s)."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from washingwood.build import FAILURES, load_archive  # build imports this module

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--report", action="store_true", required=True, help="print the calibration report")
    p.add_argument("--archive", required=True, type=Path, help="archive/<league> folder holding one folder per Season")
    p.add_argument("--owners", required=True, type=Path, help="owners.yaml (private)")
    p.add_argument("--pg", default=os.environ.get("WASHINGWOOD_PG"), help="Postgres DSN; default $WASHINGWOOD_PG")
    args = p.parse_args(argv)
    if not args.pg:
        p.error("no Postgres DSN: pass --pg or set WASHINGWOOD_PG")
    try:
        with psycopg.connect(args.pg) as conn:
            load_archive(conn, args.archive, args.owners)
            print(report(conn))
    except FAILURES as e:
        print(f"report failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
