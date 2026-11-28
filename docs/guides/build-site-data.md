# Building the site data

How to turn the private archive into the JSON the site renders. This runs on your machine only. League data never goes to the public repo or to CI (ADR-0007).

## What happens

1. The build reads `owners.yaml`, which says which ESPN accounts belong to which **Owner**.
2. It reads each Season folder in the archive (2018 onward): `league_mSettings.json`, `league_mTeam.json`, `league_mMatchupScore.json`.
3. It loads them into Postgres `core.*`. Re-running replaces each Season's rows, so a re-run is always safe.
4. It writes the site data to `export/`:
   - `league.json`: the league summary and the current Champion
   - `trophy-shelf.json`: every Owner's titles and runner-ups
   - `owners.json`: the Owners index (every Owner, with their career regular-season record)
   - `owners/<slug>.json`: one per Owner (trophy case, career summary, every Season, head-to-head)
   - `seasons/<year>.json`: one per Season (Podium, Last place, standings, Scoring format, bracket, weekly results)
   - `hall-of-fame.json`: every Hall of Fame Inductee (Season and Owner pages filter it)

   Every document is checked against `contract/site-data.schema.json` before any file is written.

The build stops, writing nothing, if:
- any team's ESPN account isn't in `owners.yaml`
- any team's ESPN accounts map to more than one Owner (a **Franchise** has exactly one Owner; see `GLOSSARY.md`). Several accounts belonging to the same Owner are fine.

Either error names the Season and the team. Fix `owners.yaml` and run the build again.

## One-time setup

1. **Start Docker Desktop.** Postgres runs in a container.
2. **Start a Postgres container:**
   ```powershell
   docker run -d --name washingwood-pg -e POSTGRES_PASSWORD=localonly -p 5432:5432 postgres:16-alpine
   ```
   - `docker run -d`: start a container in the background.
   - `--name washingwood-pg`: a name, so you can stop and start it later.
   - `-e POSTGRES_PASSWORD=localonly`: the database password. The container is local only.
   - `-p 5432:5432`: expose Postgres on your machine's port 5432.
   - `postgres:16-alpine`: the image, Postgres 16 (ADR-0003).
3. **Set the DSN in `.env`** (never committed):
   ```
   WASHINGWOOD_PG=postgresql://postgres:localonly@localhost:5432/postgres
   ```
4. **Write `owners.yaml`** in the private archive repo (format below).

## owners.yaml

```yaml
owners:
  - name: Quinn Harrow              # shown on the site; must be unique
    espn_members:                   # every ESPN account this person used
      - "{11111111-1111-1111-1111-111111111111}"
      - "{22222222-2222-2222-2222-222222222222}"
```

- One entry per real person. An Owner who switched ESPN accounts lists every account.
- Member IDs are in `league_mTeam.json` under `teams[].owners[]`.
- The name is shown on the site exactly as written, capitals included.
- The Owner's URL slug comes from the name (`Quinn Harrow` → `quinn-harrow`). Changing only capitals keeps the slug; any other rename changes it.

## Run it

```powershell
uv run --env-file .env python -m washingwood.build --archive archive/<league-id> --owners archive/owners.yaml --out export
```

- `uv run --env-file .env`: run inside the project's environment, with `.env` loaded, so `WASHINGWOOD_PG` is set.
- `python -m washingwood.build`: the build command.
- `--archive archive/<league-id>`: the league folder, which holds one folder per Season.
- `--owners archive/owners.yaml`: the Owner mapping.
- `--out export`: the output folder (gitignored).

On success it prints a `wrote ...` line for each file. On failure it prints `build failed: ...`, writes nothing, and exits 1.

## Hall of Fame calibration report

The Hall of Fame inducts a Player season when it clears a fixed **Induction bar** (ADR-0009). The bars are constants in `src/washingwood/hall_of_fame.py`: `PAR_BAR` (Dominant), `POE_BAR` (Overachiever) and `PICKUP_BAR` (Waiver legend). The report shows how many Player seasons each Season would induct at a range of candidate bars, so the bars can be chosen against the real archive.

```powershell
uv run --env-file .env python -m washingwood.hall_of_fame --report --archive archive/<league-id> --owners archive/owners.yaml
```

- `python -m washingwood.hall_of_fame`: the Hall of Fame module.
- `--report`: print the calibration report.
- `--archive`, `--owners`: the same as for the build. It loads the archive into Postgres the same way, and writes no files.
- `--par`, `--poe`, `--pickup` (optional): try other Dominant, Overachiever and Waiver legend bars in the report without editing the constants. The last column of each lane's table and the totals table then use them.

It prints one table per lane, with one row per Season: the count at each candidate bar, then the count at the current bar. A last table gives each Season's Inductees at the current bars, per lane and in total (a Player season clearing several lanes counts once in the total). It prints counts only, never a Player or Owner name, so the output is safe to paste into an issue or PR.

## Tests

`uv run pytest` runs the Seam 1 tests (`tests/test_build.py`) against invented, ESPN-shaped archives (`tests/espn_fixture.py`). Each test gets its own fresh database in a throwaway container. If Docker isn't running, those tests are skipped and say so.

## Known limits (v1)

- An existing database keeps its schema. After `db/schema.sql` changes, the build stops and says the database's schema predates it. Recreate the container, then run the build again:
  ```powershell
  docker rm -f washingwood-pg
  ```
  - `docker rm -f`: stop and delete the container, along with its database. Nothing is lost: every build reloads it from the archive.
  ```powershell
  docker run -d --name washingwood-pg -e POSTGRES_PASSWORD=localonly -p 5432:5432 postgres:16-alpine
  ```
  - The same command as in **One-time setup**. Give Postgres a few seconds to start.
- `raw.responses` isn't filled. The archive files on disk are the raw source (ADR-0001).
