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
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import psycopg
import yaml
from psycopg import Connection

from washingwood.loader import PLATFORM
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


class HallOfFameError(ValueError):
    """hall_of_fame.yaml is malformed, or one of its Owner's notes matches no Inductee."""


def load_notes(conn: Connection, path: Path | None) -> None:
    """Replace core.hall_of_fame with the Owner's notes in hall_of_fame.yaml (private, ADR-0007). No file
    leaves none, so every Inductee's ownerNote is null. Each entry names a Season (year) and an ESPN player
    ID, resolved through core.player_external_ids (ADR-0002):

        notes:
          - season: 2020
            espn_player: 90000001
            note: Carried us to the title.

    Fails, naming the Season and the ESPN player ID, on an entry that matches no Inductee."""
    conn.execute("DELETE FROM core.hall_of_fame")
    if path is None:
        return
    path = Path(path)
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = doc.get("notes") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise HallOfFameError(f"{path}: expected a 'notes' list")
    notes: dict[tuple[int, str], str] = {}
    for n, entry in enumerate(entries):
        entry = entry if isinstance(entry, dict) else {}
        year, pid, note = entry.get("season"), entry.get("espn_player"), entry.get("note")
        if not isinstance(year, int) or isinstance(year, bool):
            raise HallOfFameError(f"{path}: notes[{n}] needs 'season' as a year, e.g. 2020")
        if isinstance(pid, bool) or not re.fullmatch(r"-?\d+", str(pid)):
            raise HallOfFameError(f"{path}: notes[{n}] needs 'espn_player' as an ESPN player ID")
        if not isinstance(note, str) or not note.strip():
            raise HallOfFameError(f"{path}: Season {year}, ESPN player {pid} has no 'note'")
        key = (year, str(int(pid)))
        if key in notes:
            raise HallOfFameError(f"{path}: Season {year}, ESPN player {pid} is listed twice")
        notes[key] = note.strip()
    seasons = dict(conn.execute("SELECT year, season_id FROM core.seasons").fetchall())
    players = dict(
        conn.execute(
            "SELECT external_id, player_id FROM core.player_external_ids WHERE platform = %s AND external_id = ANY(%s)",
            (PLATFORM, [ext for _, ext in notes]),
        ).fetchall()
    )
    inducted = {(i["_season_id"], i["_player_id"]) for i in _inductees(conn)}
    for (year, ext), note in notes.items():
        season_id, player_id = seasons.get(year), players.get(ext)
        if (season_id, player_id) not in inducted:
            raise HallOfFameError(f"{path}: Season {year}, ESPN player {ext} matches no Inductee")
        conn.execute(
            "INSERT INTO core.hall_of_fame (player_id, season_id, owner_note) VALUES (%s, %s, %s)",
            (player_id, season_id, note),
        )


def _bars(trying: dict[str, float] | None = None) -> dict[str, float]:
    """Each lane's current bar, read at call time, with any the report is trying instead."""
    return {"dominant": PAR_BAR, "overachiever": POE_BAR, "waiver_legend": PICKUP_BAR, **(trying or {})}


def _lane_value(lane: str, value: Decimal) -> float | int:
    """Points over expected is whole points; the other two are rounded to 2 decimals."""
    return int(value) if lane == "overachiever" else round(float(value), 2)


def inductees(conn: Connection) -> list[dict]:
    """Every Inductee: one per Player season that clears at least one bar, carrying every lane it cleared (in
    credit order, each with its value and Owner ref) and credited to its first lane's Owner, with the card
    back's moments and the Owner's note (null until written). Newest Season first, then highest Points above
    replacement, then Player name."""
    out = []
    for i in _inductees(conn):
        season_id, player_id, franchise_id = i.pop("_season_id"), i.pop("_player_id"), i.pop("_franchise_id")
        refs = i.pop("_refs")
        i["moments"] = _moments(conn, season_id, player_id, franchise_id, refs)
        i["ownerNote"] = i.pop("_note")
        out.append(i)
    return out


def _inductees(conn: Connection, trying: dict[str, float] | None = None) -> list[dict]:
    """The Inductees' card fronts, in order, each with private keys: _season_id, _player_id, the credited
    _franchise_id, its Owner's _note and _refs (every Franchise's Owner ref and team name). `trying` swaps in
    other bars (the report)."""
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
            SELECT k.season_id, k.player_id, hof.owner_note, s.year, s.scoring_label, p.full_name, ps.position,
                   ps.nfl_team, ps.season_points, psf.positional_finish, {lane_cols}
            FROM k
            JOIN core.seasons s                      ON s.season_id = k.season_id
            JOIN core.players p                      ON p.player_id = k.player_id
            JOIN core.player_seasons ps              ON ps.season_id = k.season_id AND ps.player_id = k.player_id
            LEFT JOIN stats.player_season_finish psf ON psf.season_id = k.season_id AND psf.player_id = k.player_id
            LEFT JOIN core.hall_of_fame hof          ON hof.season_id = k.season_id AND hof.player_id = k.player_id
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
    for season_id, player_id, note, year, label, name, position, nfl_team, points, finish, *by_lane in rows:
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
                "_season_id": season_id,
                "_player_id": player_id,
                "_franchise_id": cleared_lanes[0][1],
                "_note": note,
                "_refs": franchises,
            }
        )
    return out


def _moments(conn: Connection, season_id: int, player_id: int, franchise_id: int, refs: dict) -> dict:
    """The card back's moments, all for the credited Franchise: the Player's best Week, his starter points in
    championship-bracket Matchups and in the championship game, the Franchise's finish and his Weeks started."""
    ids = {"s": season_id, "p": player_id, "f": franchise_id}
    # Best Week: his highest starter score in a Counted Matchup (so never a two-Week round); a tie goes to the
    # earlier Week. A Week he didn't play (no points) doesn't count.
    best = conn.execute(
        """SELECT c.week, le.points,
                  CASE WHEN c.home_franchise_id = le.franchise_id THEN c.away_franchise_id
                       ELSE c.home_franchise_id END,
                  c.winner_franchise_id
           FROM core.lineup_entries le
           JOIN stats.counted_matchups c ON c.season_id = le.season_id AND c.week = le.week
                                        AND le.franchise_id IN (c.home_franchise_id, c.away_franchise_id)
           WHERE le.season_id = %(s)s AND le.player_id = %(p)s AND le.franchise_id = %(f)s
             AND le.is_starter AND le.points IS NOT NULL
           ORDER BY le.points DESC, c.week
           LIMIT 1""",
        ids,
    ).fetchone()
    best_week = None
    if best is not None:
        week, points, opponent, winner = best
        result = "tie" if winner is None else "win" if winner == franchise_id else "loss"
        best_week = {"week": week, "points": float(points), "opponent": refs[opponent][0], "result": result}
    # The championship-bracket Matchups the Franchise played (a bye isn't played), every Week of a two-Week
    # round included, with his starter points in each: 0 when he didn't start. None in a Season with no lineups.
    games = conn.execute(
        """SELECT m.is_championship, coalesce(sum(le.points) FILTER (WHERE le.is_starter), 0)
           FROM core.matchups m
           LEFT JOIN core.lineup_entries le
                  ON le.season_id = m.season_id AND le.franchise_id = %(f)s AND le.player_id = %(p)s
                 AND le.week BETWEEN m.first_week AND m.last_week
           WHERE m.season_id = %(s)s AND m.is_playoff AND m.bracket = 'winners' AND m.away_franchise_id IS NOT NULL
             AND %(f)s IN (m.home_franchise_id, m.away_franchise_id)
             AND EXISTS (SELECT 1 FROM core.lineup_entries x WHERE x.season_id = %(s)s)
           GROUP BY m.matchup_id, m.is_championship""",
        ids,
    ).fetchall()
    playoff = round(float(sum(points for _, points in games)), 2) if games else None
    championship = next((round(float(points), 2) for is_final, points in games if is_final), None)
    final_rank, seed, made, started = conn.execute(
        """SELECT f.final_rank, f.playoff_seed, f.playoff_seed <= s.playoff_team_count,
                  (SELECT count(*) FROM core.lineup_entries le
                   WHERE le.season_id = %(s)s AND le.player_id = %(p)s AND le.franchise_id = %(f)s AND le.is_starter)
           FROM core.franchises f
           JOIN core.seasons s ON s.season_id = f.season_id
           WHERE f.franchise_id = %(f)s""",
        ids,
    ).fetchone()
    return {
        "bestWeek": best_week,
        "playoffPoints": playoff,
        "championshipPoints": championship,
        "finish": {"finalRank": final_rank, "playoffSeed": seed, "madePlayoffs": made},
        "weeksStarted": started,
    }


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
    per_season = Counter(i["year"] for i in _inductees(conn, trying))
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
