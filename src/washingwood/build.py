"""One command: archive + owners.yaml -> Postgres core.* -> site-data JSON.

    uv run python -m washingwood.build --archive ../washingwood-archive/<league> \
        --owners ../washingwood-archive/owners.yaml --out export/

The Postgres DSN comes from --pg or WASHINGWOOD_PG. It is never printed (it may hold a password).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

from washingwood import contract, export
from washingwood.loader import LoadError, SeasonFiles, load_season
from washingwood.owners import OwnerMappingError, load_owners

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
FIRST_SEASON = 2018  # recorded history starts here (GLOSSARY: League)


class BuildError(Exception):
    """The build stopped; the message says why."""


def build(archive_dir: Path, owners_file: Path, out_dir: Path, dsn: str) -> list[Path]:
    """Load every Season in `archive_dir` and write the site data to `out_dir`. Returns files written."""
    archive_dir, out_dir = Path(archive_dir), Path(out_dir)
    owner_map = load_owners(Path(owners_file))
    season_dirs = sorted(
        (d for d in archive_dir.iterdir() if d.is_dir() and d.name.isdigit() and int(d.name) >= FIRST_SEASON),
        key=lambda d: int(d.name),
    )
    if not season_dirs:
        raise BuildError(f"no Season folders ({FIRST_SEASON}+) in {archive_dir}")

    with psycopg.connect(dsn) as conn:
        _ensure_schema(conn)
        for d in season_dirs:
            with conn.transaction():
                load_season(conn, SeasonFiles.read(d), owner_map)
        docs = {"league.json": (export.league_summary(conn), "league")}

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (doc, kind) in docs.items():
        contract.validate(doc, kind)
        path = out_dir / name
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written


def _ensure_schema(conn: psycopg.Connection) -> None:
    """Create the schema on an empty database. An existing one is left alone (no migrations yet)."""
    if conn.execute("SELECT to_regclass('core.seasons')").fetchone()[0] is None:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.commit()
    elif conn.execute("SELECT to_regclass('stats.champions')").fetchone()[0] is None:
        raise BuildError("the database's schema predates db/schema.sql: drop and recreate the database, then re-run")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--archive", required=True, type=Path, help="archive/<league> folder holding one folder per Season")
    p.add_argument("--owners", required=True, type=Path, help="owners.yaml (private)")
    p.add_argument("--out", default=Path("export"), type=Path, help="output folder (gitignored); default export/")
    p.add_argument("--pg", default=os.environ.get("WASHINGWOOD_PG"), help="Postgres DSN; default $WASHINGWOOD_PG")
    args = p.parse_args(argv)
    if not args.pg:
        p.error("no Postgres DSN: pass --pg or set WASHINGWOOD_PG")
    try:
        written = build(args.archive, args.owners, args.out, args.pg)
    except (BuildError, OwnerMappingError, LoadError, contract.ContractError) as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    except psycopg.OperationalError as e:
        # psycopg's message names host/user but not the password; still, never echo the DSN itself
        print(f"build failed: can't use the Postgres database ({type(e).__name__}: {e})", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
