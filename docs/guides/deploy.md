# Deploying the site

How v1 gets from the private archive to `washingwood.xyz`. Everything runs on your machine. League data never goes through this public repo or CI (ADR-0007), and no ESPN access is needed.

## What the deploy command does

```powershell
uv run --env-file .env python -m washingwood.deploy --archive archive/<league-id> --owners archive/owners.yaml --hall-of-fame archive/hall_of_fame.yaml
```

- `uv run --env-file .env`: run in the project's environment with `.env` loaded, so `WASHINGWOOD_PG` is set.
- `python -m washingwood.deploy`: the deploy command (`src/washingwood/deploy.py`).
- `--archive archive/<league-id>`: the league folder in the private archive repo.
- `--owners archive/owners.yaml`: the Owner mapping (private).
- `--hall-of-fame archive/hall_of_fame.yaml` (optional): the Owner's notes for Hall of Fame cards (private; format in `docs/guides/build-site-data.md`). Leave it out and every card says "Owner's note coming soon".
- Add `--dry-run` to build everything without uploading.

It runs three steps, and stops at the first failure:

1. **Builds the site data** into `export/` (gitignored). This is also the real-archive check. The build stops unless every Season:
   - has one Champion whose win agrees with ESPN's final places
   - has a Third-place game whose winner ESPN ranks 3rd
   - has Podium places exactly 1, 2 and 3
   - has a Last place that is the worst seed
   - produces documents that pass the contract
   - with `--hall-of-fame`: has an Inductee for every Owner's note in the file
2. **Builds the static site** into `site/dist/` (gitignored) from that data.
3. **Uploads `site/dist/`** to the Cloudflare Pages project `washingwood` on the `main` (production) branch, using Wrangler.

Before writing anything, it refuses to run if `export/` or `site/dist/` isn't gitignored.

## First deploy (one time)

1. **Start Postgres and set `.env`:** see "One-time setup" in `docs/guides/build-site-data.md`.
2. **Log in to Cloudflare:** run `npx wrangler login` in `site/`.
3. **Create the Pages project:** run `npx wrangler pages project create washingwood --production-branch main` in `site/`.
4. **Set both secrets:**
   - Run `npx wrangler pages secret put SITE_PASSPHRASE --project-name washingwood`.
   - Run `npx wrangler pages secret put SESSION_KEY --project-name washingwood`.
   - Wrangler prompts for each value, so it never lands in your shell history.
5. **Deploy:** run the command above.
6. **Connect `washingwood.xyz`:** in the Cloudflare dashboard, go to Workers & Pages → washingwood → Custom domains.
7. **Add the rate-limiting rule:** see "Deploy checklist" in `docs/guides/site.md`.
8. **Check the gate on the live site:** without a cookie, a page redirects to `/enter/`, and an image or data path returns 401.

## Every year after that

See "Yearly update" in `docs/GAMEPLAN.md`. Archive the new Season, push it to the private repo, then run the deploy command.
