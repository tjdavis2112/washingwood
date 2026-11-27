#!/usr/bin/env python3
"""Archive every raw ESPN response for a league, season by season.

Writes untouched JSON to disk (and optionally to Postgres raw.responses) so the
league's history no longer depends on ESPN. Normalizing into core.* is a
separate step that reads from this archive.

    python scripts/archive_espn.py --league-id 123456 --years 2018-2025 \
        --espn-s2 "$ESPN_S2" --swid "$ESPN_SWID" --out archive/

    # Weekly refresh: past seasons come from disk, the live season is refetched
    python scripts/archive_espn.py --league-id 123456 --years 2025

Layout:
    archive/<league>/<year>/<resource>.json
    archive/<league>/<year>/<resource>_w<NN>.json   (per-week calls)
    archive/<league>/manifest.jsonl                 (one line per call, incl. failures)
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# League-level views, fetched one per call so each raw file has one meaning.
SEASON_VIEWS = ["mSettings", "mStatus", "mTeam", "mRoster", "mMatchupScore", "mStandings", "mDraftDetail"]

# Seasons where ESPN returns player-level weekly data. Earlier years are archival.
FULL_DATA_FROM = 2019


def current_season(today=None):
    """NFL fantasy season in progress: Aug-Dec is this year, Jan-Jul is last year."""
    today = today or dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


class Archiver:
    def __init__(self, league_id, out_dir, cookies, delay, pg_dsn=None, force=False):
        self.league_id = str(league_id)
        self.out = Path(out_dir) / self.league_id
        self.out.mkdir(parents=True, exist_ok=True)
        self.manifest = open(self.out / "manifest.jsonl", "a", encoding="utf-8")
        self.session = requests.Session()
        if cookies:
            self.session.cookies.update(cookies)
        self.delay = delay
        self.force = force
        self.route = {}  # year -> 'seasons' | 'history', remembered after a 401 fallback
        self.pg = None
        if pg_dsn:
            import psycopg  # pip install "psycopg[binary]"
            self.pg = psycopg.connect(pg_dsn, autocommit=True)

    # -- URL helpers ---------------------------------------------------------

    def league_url(self, year, route):
        if route == "history":
            return f"{BASE}/leagueHistory/{self.league_id}", {"seasonId": year}
        return f"{BASE}/seasons/{year}/segments/0/leagues/{self.league_id}", {}

    # -- HTTP ----------------------------------------------------------------

    def _get(self, url, params, headers):
        for attempt in range(4):
            r = self.session.get(url, params=params, headers=headers, timeout=30)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * max(self.delay, 1))
                continue
            return r
        return r

    def fetch(self, year, resource, params, *, week=None, filters=None, league=True, extend=""):
        """Fetch one resource, save it, and return the parsed payload (or None)."""
        name = f"{resource}_w{week:02d}" if week is not None else resource
        path = self.out / str(year) / f"{name}.json"
        # Past seasons are immutable: reuse the archived copy. The live season always refetches.
        if path.exists() and not self.force and year < current_season():
            return json.loads(path.read_text(encoding="utf-8"))

        headers = {"x-fantasy-filter": json.dumps(filters)} if filters else None

        if league:
            route = self.route.get(year, "history" if year < 2018 else "seasons")
            url, base_params = self.league_url(year, route)
            r = self._get(url + extend, {**base_params, **params}, headers)
            if r.status_code == 401:  # same fallback the espn_api package uses
                alt = "seasons" if route == "history" else "history"
                url, base_params = self.league_url(year, alt)
                r2 = self._get(url + extend, {**base_params, **params}, headers)
                if r2.status_code == 200:
                    self.route[year] = alt
                    r = r2
            full_url = url + extend
            full_params = {**base_params, **params}
        else:
            full_url = f"{BASE}/seasons/{year}{extend}"
            full_params = params
            r = self._get(full_url, full_params, headers)

        time.sleep(self.delay)

        entry = {
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "season": year, "resource": resource, "week": week,
            "url": full_url, "params": full_params, "filters": filters,
            "status": r.status_code,
        }

        if r.status_code != 200:
            entry["error"] = r.text[:300]
            self._log(entry)
            print(f"  ! {year} {name}: HTTP {r.status_code}", file=sys.stderr)
            return None

        body = r.content
        payload = r.json()
        # leagueHistory returns a one-element list
        if isinstance(payload, list) and len(payload) == 1 and league:
            payload = payload[0]

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        entry["sha256"] = hashlib.sha256(body).hexdigest()
        entry["bytes"] = len(body)
        entry["file"] = str(path.relative_to(self.out))
        self._log(entry)
        self._to_pg(year, resource, week, full_url, full_params, entry["sha256"], payload)
        print(f"  {year} {name}: {len(body):,} bytes")
        return payload

    def _log(self, entry):
        self.manifest.write(json.dumps(entry) + "\n")
        self.manifest.flush()

    def _to_pg(self, year, resource, week, url, params, sha, payload):
        if not self.pg:
            return
        self.pg.execute(
            """INSERT INTO raw.responses
                 (platform, league_ext_id, season, resource, scoring_period, url, params, sha256, payload)
               VALUES ('espn', %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (self.league_id, year, resource, week, url, json.dumps(params), sha, json.dumps(payload)),
        )

    # -- Season walk ---------------------------------------------------------

    def archive_season(self, year):
        print(f"Season {year}")
        payloads = {}
        for view in SEASON_VIEWS:
            payloads[view] = self.fetch(year, f"league_{view}", {"view": view})

        settings = payloads.get("mSettings") or {}
        status = (payloads.get("mStatus") or {}).get("status") or settings.get("status") or {}

        # Pro schedule (byes, opponents) and the player pool for name/ID mapping
        self.fetch(year, "pro_schedule", {"view": "proTeamSchedules_wl"}, league=False)
        self.fetch(year, "players", {"view": "players_wl"}, league=False, extend="/players",
                   filters={"filterActive": {"value": True}})

        if year < FULL_DATA_FROM:
            print("  (archival season: skipping per-week calls)")
            return

        # Every player with season stats, rostered or not (for draft value)
        self.fetch(year, "player_pool", {"view": "kona_player_info", "scoringPeriodId": 0},
                   filters={"players": {"limit": 2000,
                                        "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})

        # Per-week: box scores (lineups + player stats), rosters, transactions
        matchup_periods = settings.get("settings", {}).get("scheduleSettings", {}).get("matchupPeriods", {})
        week_to_period = {w: int(mp) for mp, weeks in matchup_periods.items() for w in weeks}
        last_week = status.get("latestScoringPeriod") or status.get("finalScoringPeriod") or 17
        last_week = min(last_week, status.get("finalScoringPeriod") or last_week)

        for week in range(1, last_week + 1):
            period = week_to_period.get(week, week)
            self.fetch(year, "boxscore", {"view": ["mMatchupScore", "mScoreboard"], "scoringPeriodId": week},
                       week=week, filters={"schedule": {"filterMatchupPeriodIds": {"value": [period]}}})
            self.fetch(year, "roster", {"view": "mRoster", "scoringPeriodId": week}, week=week)
            self.fetch(year, "transactions", {"view": "mTransactions2", "scoringPeriodId": week}, week=week)

        self.archive_activity(year)

    def archive_activity(self, year, page_size=50):
        """Activity feed (adds/drops/trades), paged until exhausted."""
        offset, page = 0, 0
        while True:
            filters = {"topics": {
                "filterType": {"value": ["ACTIVITY_TRANSACTIONS"]},
                "limit": page_size, "limitPerMessageSet": {"value": 25}, "offset": offset,
                "sortMessageDate": {"sortPriority": 1, "sortAsc": False},
                "sortFor": {"sortPriority": 2, "sortAsc": False},
                "filterIncludeMessageTypeIds": {"value": [178, 179, 180, 181, 239, 244]},
            }}
            data = self.fetch(year, f"activity_p{page:03d}", {"view": "kona_league_communication"},
                              filters=filters, extend="/communication/")
            topics = (data or {}).get("topics", [])
            if len(topics) < page_size:
                break
            offset += page_size
            page += 1


def parse_years(spec):
    years = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            years.update(range(int(a), int(b) + 1))
        else:
            years.add(int(part))
    return sorted(years)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league-id", required=True)
    p.add_argument("--years", required=True, help="e.g. 2018-2025 or 2019,2021")
    p.add_argument("--espn-s2", default=os.environ.get("ESPN_S2"))
    p.add_argument("--swid", default=os.environ.get("ESPN_SWID"))
    p.add_argument("--out", default="archive")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    p.add_argument("--pg", default=os.environ.get("WASHINGWOOD_PG"), help="Postgres DSN for raw.responses")
    p.add_argument("--force", action="store_true", help="refetch files that already exist")
    args = p.parse_args()

    cookies = {}
    if args.espn_s2 and args.swid:
        cookies = {"espn_s2": args.espn_s2, "SWID": args.swid}

    arch = Archiver(args.league_id, args.out, cookies, args.delay, args.pg, args.force)
    for year in parse_years(args.years):
        arch.archive_season(year)
    print(f"Done. Manifest: {arch.out / 'manifest.jsonl'}")


if __name__ == "__main__":
    main()
