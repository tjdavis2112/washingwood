# Raw archive is the source of truth; core and stats are rebuilt from it

ESPN can drop old seasons or change its API at any time, so every response is saved untouched (on disk, optionally in `raw.responses`) before anything is parsed. Data flows one way, `raw` → `core` → `stats`, and each layer can be rebuilt from the one before it. A loader bug or schema change costs a reload, not lost history.

## Consequences

- Never edit archive files or `raw.responses` rows. Fix the loader instead.
- The loader must be idempotent per season, because re-running it is the normal recovery path.
- Past-season files are reused from disk; only the live season is refetched (`--force` overrides).
