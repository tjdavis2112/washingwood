"""One command: archive -> site data -> static site -> Cloudflare Pages.

    uv run --env-file .env python -m washingwood.deploy --archive ../washingwood-archive/<league-id> \
        --owners ../washingwood-archive/owners.yaml --hall-of-fame ../washingwood-archive/hall_of_fame.yaml

Runs on the maintainer's machine only. League data never goes through the public repo or CI
(ADR-0007): it is written to the gitignored export/ and site/dist/ folders and uploaded straight
to Cloudflare by Wrangler. Needs no ESPN access. --hall-of-fame (Owner's notes) is optional.

1. Build the site data (washingwood.build). This is also the real-archive invariant check: the
   build stops unless every Season has one Champion that agrees with ESPN's final places, a
   three-place Podium, a Last place that is the worst seed, and contract-valid documents.
2. Build the static site from that data (astro build, SITE_DATA_DIR=export/).
3. Upload site/dist/ with `wrangler pages deploy` (skipped with --dry-run).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from washingwood import build as site_data

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
EXPORT = REPO / "export"


class DeployError(Exception):
    """The deploy stopped; the message says why."""


def _tool(name: str) -> str:
    # On Windows npm/npx are .cmd files, which subprocess finds only by full path
    path = shutil.which(name)
    if not path:
        raise DeployError(f"{name} not found: install Node.js, then run `npm install` in site/")
    return path


def _ensure_gitignored(path: Path) -> None:
    """Refuse to write league data anywhere git would pick it up (ADR-0007)."""
    # Ask about a file inside: a `folder/` rule only matches a folder that already exists
    result = subprocess.run(["git", "check-ignore", "-q", str(path / "probe.json")], cwd=REPO)
    if result.returncode != 0:
        raise DeployError(f"{path} is not gitignored: refusing to write league data there")


def _run(cmd: list[str], *, env: dict | None = None) -> None:
    print("  $", " ".join(Path(cmd[0]).name if i == 0 else c for i, c in enumerate(cmd)), flush=True)
    if subprocess.run(cmd, cwd=SITE, env=env).returncode != 0:
        raise DeployError(f"{Path(cmd[0]).name} failed (see its output above)")


def deploy(
    archive: Path,
    owners: Path,
    dsn: str,
    project: str,
    branch: str,
    dry_run: bool,
    hall_of_fame_file: Path | None = None,
) -> None:
    for path in (EXPORT, SITE / "dist"):
        _ensure_gitignored(path)

    print("1/3 Building site data from the archive (and checking every Season)...", flush=True)
    shutil.rmtree(EXPORT, ignore_errors=True)  # no stale Seasons from an earlier run
    for path in site_data.build(archive, owners, EXPORT, dsn, hall_of_fame_file=hall_of_fame_file):
        print(f"  wrote {path.relative_to(REPO)}")

    print("2/3 Building the static site...", flush=True)
    _run([_tool("npx"), "astro", "build"], env={**os.environ, "SITE_DATA_DIR": str(EXPORT)})

    if dry_run:
        print("3/3 Skipped upload (--dry-run). The built site is in site/dist/.")
        return
    print(f"3/3 Uploading to Cloudflare Pages project '{project}' ({branch})...", flush=True)
    _run([_tool("npx"), "wrangler", "pages", "deploy", "dist", "--project-name", project, "--branch", branch])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build the site from the archive and deploy it to Cloudflare Pages.")
    p.add_argument("--archive", required=True, type=Path, help="archive/<league-id> folder")
    p.add_argument("--owners", required=True, type=Path, help="owners.yaml (private)")
    p.add_argument("--hall-of-fame", type=Path, help="hall_of_fame.yaml, the Owner's notes (private; optional)")
    p.add_argument("--pg", default=os.environ.get("WASHINGWOOD_PG"), help="Postgres DSN; default $WASHINGWOOD_PG")
    p.add_argument("--project", default="washingwood", help="Cloudflare Pages project name")
    p.add_argument("--branch", default="main", help="Pages branch; main is production")
    p.add_argument("--dry-run", action="store_true", help="build everything but don't upload")
    args = p.parse_args(argv)
    if not args.pg:
        p.error("no Postgres DSN: pass --pg or set WASHINGWOOD_PG")
    try:
        deploy(
            args.archive,
            args.owners,
            args.pg,
            args.project,
            args.branch,
            args.dry_run,
            hall_of_fame_file=args.hall_of_fame,
        )
    except (DeployError, *site_data.FAILURES) as e:
        print(f"deploy failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
