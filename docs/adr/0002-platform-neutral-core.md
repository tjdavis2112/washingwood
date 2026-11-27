# Core model is platform-neutral; platform IDs live only in external_ids tables

The league may move from ESPN to Sleeper or Yahoo. `core.*` uses its own serial keys, and ESPN IDs (SWIDs, team IDs, player IDs, stat IDs) live only in `owner_external_ids`, `player_external_ids`, `league_platforms` and `stat_definitions`. Switching platforms then means writing a new importer, not migrating the schema.

## Considered Options

- **Use ESPN IDs as primary keys**: simpler loader, but every table would need rekeying on a platform switch, and cross-platform player matching would be impossible. Rejected.

## Consequences

- Player stats are stored as canonical keys (`rec`, `rush_yds`), not ESPN stat IDs, so any season can be re-scored under any format.
- The loader needs a lookup step for every external ID.
