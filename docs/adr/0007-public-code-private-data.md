# Code repo is public; league data lives only in a private repo and the deployed site

`tjdavis2112/washingwood` is a public GitHub repo, and anything committed there skips the site's passphrase (ADR-0006). League data therefore never enters it: the raw **Archive**, `owners.yaml` (real names ↔ ESPN IDs), **Punishment** content and the exported site JSON. The Archive, `owners.yaml` and Punishment content live in a private repo, `washingwood-archive`. The exported JSON is built locally and uploaded straight to Cloudflare, never committed.

## Considered Options

- **Make the code repo private**: simpler, but it relies on one setting staying correct forever, and code doesn't need hiding. Rejected in favor of keeping data out entirely.
- **Deploy from GitHub Actions**: the data or ESPN cookies would have to live in CI, which isn't worth it for a once-a-year job. Rejected: deploys run from your machine.

## Consequences

- Real owner names don't appear in code, tests, fixtures, ADRs or issues. Tests use invented names.
- `.gitignore` excludes `archive/`, `owners.yaml`, `.env` and build output. Check new data paths against it.
- Rebuilding on a new machine needs both repos cloned plus `.env`.
