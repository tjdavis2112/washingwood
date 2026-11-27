# Owners are mapped to people by hand, not taken from ESPN identities

ESPN members don't line up with real people across 10+ years: accounts change, franchises get co-owners, and old seasons may expose only team IDs. A hand-maintained `owners.yaml` maps ESPN SWIDs and team IDs to a person per **Season**, and the loader reads it to fill `core.owners` and `core.franchise_owners`.

## Consequences

- A new owner or account change needs an `owners.yaml` edit before the loader runs. The loader should fail loudly on an unmapped franchise rather than guess.
- `owners.yaml` holds league members' names and ESPN IDs. Treat it as private.
