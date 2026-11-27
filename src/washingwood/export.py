"""Export site-data documents (contract/site-data.schema.json) from core.* and stats.*.

Output is deterministic: stable ordering, no timestamps.
"""

from __future__ import annotations

from psycopg import Connection

from washingwood.owners import slugify


def league_summary(conn: Connection) -> dict:
    seasons = conn.execute("SELECT year, team_count FROM core.seasons ORDER BY year").fetchall()
    if not seasons:
        raise ValueError("no Seasons loaded")
    latest = seasons[-1][0]
    champ = conn.execute("SELECT display_name, team_name FROM stats.champions WHERE year = %s", (latest,)).fetchall()
    if len(champ) != 1:
        raise ValueError(f"Season {latest}: expected one Champion, found {len(champ)}")
    name, team_name = champ[0]
    league_name = conn.execute(
        "SELECT l.name FROM core.leagues l JOIN core.seasons s USING (league_id) WHERE s.year = %s", (latest,)
    ).fetchone()[0]
    return {
        "leagueName": league_name,
        "seasons": [{"year": y, "teamCount": n} for y, n in seasons],
        "champion": {"owner": {"slug": slugify(name), "name": name}, "teamName": team_name, "year": latest},
    }
