"""One command: archive + owners.yaml -> Postgres core.* -> site-data JSON.

    uv run python -m washingwood.build --archive ../washingwood-archive/<league> \
        --owners ../washingwood-archive/owners.yaml --out export/ \
        --hall-of-fame ../washingwood-archive/hall_of_fame.yaml

--hall-of-fame (Owner's notes) is optional: without it every Inductee's ownerNote is null.

The Postgres DSN comes from --pg or WASHINGWOOD_PG. It is never printed (it may hold a password).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

from washingwood import contract, export, hall_of_fame
from washingwood.loader import LoadError, SeasonFiles, load_season
from washingwood.owners import OwnerMappingError, load_owners

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
FIRST_SEASON = 2018  # recorded history starts here (GLOSSARY: League)


class BuildError(Exception):
    """The build stopped; the message says why."""


# Failures with a clear message of their own: commands print them without a traceback.
# (psycopg's connection errors name host and user, never the password; the DSN itself is never echoed.)
FAILURES = (
    BuildError,
    OwnerMappingError,
    LoadError,
    export.ExportError,
    contract.ContractError,
    hall_of_fame.HallOfFameError,
    psycopg.OperationalError,
)


def build(
    archive_dir: Path, owners_file: Path, out_dir: Path, dsn: str, hall_of_fame_file: Path | None = None
) -> list[Path]:
    """Load every Season in `archive_dir`, and the Owner's notes in `hall_of_fame_file` when given, and write
    the site data to `out_dir`. Returns files written."""
    out_dir = Path(out_dir)
    with psycopg.connect(dsn) as conn:
        season_dirs = load_archive(conn, archive_dir, owners_file)
        with conn.transaction():
            hall_of_fame.load_notes(conn, hall_of_fame_file)
        docs = {
            "league.json": (export.league_summary(conn), "league"),
            "trophy-shelf.json": (export.trophy_shelf(conn), "trophyShelf"),
            "owners.json": (export.owner_index(conn), "ownerIndex"),
            "draft.json": (export.draft_history(conn), "draft"),
            "matchups.json": (export.matchups_document(conn), "matchups"),
            "record-book.json": (export.record_book_document(conn), "recordBook"),
            "transactions.json": (export.transactions_document(conn), "transactions"),
            "hall-of-fame.json": (hall_of_fame.hall_of_fame_document(conn), "hallOfFame"),
        }
        for slug, doc in export.owner_documents(conn).items():
            docs[f"owners/{slug}.json"] = (doc, "owner")
        for pair, doc in export.rivalry_documents(conn).items():
            docs[f"rivalries/{pair}.json"] = (doc, "rivalry")
        for year, doc in export.box_score_documents(conn).items():
            docs[f"box-scores/{year}.json"] = (doc, "boxScores")
        for d in season_dirs:
            docs[f"seasons/{d.name}.json"] = (export.season_document(conn, int(d.name)), "season")

    # Validate everything before writing anything, so a failed build leaves no partial output
    for doc, kind in docs.values():
        contract.validate(doc, kind)
    written = []
    for name, (doc, _) in docs.items():
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written


def load_archive(conn: psycopg.Connection, archive_dir: Path, owners_file: Path) -> list[Path]:
    """Load every Season folder (FIRST_SEASON on) in `archive_dir` into Postgres. Returns the folders, oldest first."""
    archive_dir = Path(archive_dir)
    owner_map = load_owners(Path(owners_file))
    season_dirs = sorted(
        (d for d in archive_dir.iterdir() if d.is_dir() and d.name.isdigit() and int(d.name) >= FIRST_SEASON),
        key=lambda d: int(d.name),
    )
    if not season_dirs:
        raise BuildError(f"no Season folders ({FIRST_SEASON}+) in {archive_dir}")
    _ensure_schema(conn)
    for d in season_dirs:
        with conn.transaction():
            load_season(conn, SeasonFiles.read(d), owner_map)
    return season_dirs


def _ensure_schema(conn: psycopg.Connection) -> None:
    """Create the schema on an empty database. An existing one is left alone (no migrations yet)."""
    if conn.execute("SELECT to_regclass('core.seasons')").fetchone()[0] is None:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.commit()
    elif (
        conn.execute("SELECT to_regclass('stats.waiver_legend_seasons')").fetchone()[0] is None  # newest object
        or conn.execute(  # newest reshape: core.hall_of_fame holds Owner's notes (#75)
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'core' AND table_name = 'hall_of_fame' AND column_name = 'owner_note'"""
        ).fetchone()
        is None
    ):
        raise BuildError("the database's schema predates db/schema.sql: drop and recreate the database, then re-run")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--archive", required=True, type=Path, help="archive/<league> folder holding one folder per Season")
    p.add_argument("--owners", required=True, type=Path, help="owners.yaml (private)")
    p.add_argument("--hall-of-fame", type=Path, help="hall_of_fame.yaml, the Owner's notes (private; optional)")
    p.add_argument("--out", default=Path("export"), type=Path, help="output folder (gitignored); default export/")
    p.add_argument("--pg", default=os.environ.get("WASHINGWOOD_PG"), help="Postgres DSN; default $WASHINGWOOD_PG")
    args = p.parse_args(argv)
    if not args.pg:
        p.error("no Postgres DSN: pass --pg or set WASHINGWOOD_PG")
    try:
        written = build(args.archive, args.owners, args.out, args.pg, hall_of_fame_file=args.hall_of_fame)
    except FAILURES as e:
        print(f"build failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
