# Building the site data

How to turn the private archive into the JSON the site renders. This runs on your machine only. League data never goes to the public repo or to CI (ADR-0007).

## What happens

1. The build reads `owners.yaml`, which says which ESPN accounts belong to which **Owner**.
2. It reads each Season folder in the archive (2018 onward): `league_mSettings.json`, `league_mTeam.json`, `league_mMatchupScore.json`.
3. It loads them into Postgres `core.*`. Re-running replaces each Season's rows, so a re-run is always safe.
4. It writes `export/league.json` and checks it against `contract/site-data.schema.json` before writing.

The build stops, writing nothing, if any team's ESPN account isn't in `owners.yaml`. The error names the Season and the team.

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
- The Owner's URL slug comes from the name (`Quinn Harrow` → `quinn-harrow`). Renaming an Owner changes their slug.

## Run it

```powershell
uv run --env-file .env python -m washingwood.build --archive archive/<league-id> --owners archive/owners.yaml --out export
```

- `uv run --env-file .env`: run inside the project's environment, with `.env` loaded, so `WASHINGWOOD_PG` is set.
- `python -m washingwood.build`: the build command.
- `--archive archive/<league-id>`: the league folder, which holds one folder per Season.
- `--owners archive/owners.yaml`: the Owner mapping.
- `--out export`: the output folder (gitignored).

On success it prints `wrote export\league.json`. On failure it prints `build failed: ...` and exits 1.

## Tests

`uv run pytest` runs the Seam 1 tests (`tests/test_build.py`) against invented, ESPN-shaped archives (`tests/espn_fixture.py`). Each test gets its own fresh database in a throwaway container. If Docker isn't running, those tests are skipped and say so.

## Known limits (v1)

- An existing database keeps its schema. After `db/schema.sql` changes, drop and recreate the container's database.
- `raw.responses` isn't filled. The archive files on disk are the raw source (ADR-0001).
