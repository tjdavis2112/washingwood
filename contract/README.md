# Site-data contract

The site-data contract is the interface between the **pipeline** (Python: archive → Postgres → JSON) and the **site** (Astro). The pipeline's exporter writes these JSON documents and the site renders only from them. Both sides test against the same schema, so they can't drift apart without a test failing.

## Files

| Path | What it is |
| --- | --- |
| `site-data.schema.json` | The JSON Schema (draft 2020-12). Every field has a `description`, so this file is the field reference. |
| `examples/league.json` | Example league summary |
| `examples/trophy-shelf.json` | Example trophy shelf |
| `examples/seasons/2018.json` | Example 10-team Season: 4 playoff teams, two-week playoff rounds, a tie, one manual score adjustment, and a Last place who wins a consolation Matchup |
| `examples/seasons/2020.json` | Example 12-team Season: 6 playoff teams, first-round byes, the Third-place game and a 5th-place Matchup |

Every Owner and team name in `examples/` is invented (ADR-0007). The real exported data goes to the gitignored `export/` folder and is never committed.

## Document kinds

The schema has one entry point per document under `$defs`:

| Kind | Entry point | Exported as |
| --- | --- | --- |
| League summary | `#/$defs/league` | `league.json` |
| Trophy shelf | `#/$defs/trophyShelf` | `trophy-shelf.json` |
| Season | `#/$defs/season` | `seasons/<year>.json` |

## Conventions

- **Owners** are always `{"slug", "name"}`. The slug is stable and URL-safe, and is never an ESPN ID (ADR-0002). A given slug carries the same name in every document.
- **Unknown fields are rejected** (`additionalProperties: false` everywhere). To add a field, change the schema first.
- **Matchups** share one rule set:
  - A bye has `away: null`, `winner: null`, `isTie: false`, and its home score may be null.
  - Otherwise both scores are numbers. A tie has `winner: null`, and anything else has `winner` set to `"home"` or `"away"`.
- **Two-week rounds** list both Weeks in `weeks`, and their scores are combined.
- **Last place** is the highest `playoffSeed`, not the bottom of `standings`.
- **`punishment`** is always present and is `null` in v1.
- **Season sections join as they're exported.** A Season document must have `year`, `teamCount`, `dataTier`, `podium`, `lastPlace`, `scoringFormat`, `standings` and `bracket`. `weeklyResults` is validated when present, and becomes required when #10 exports it. The example fixtures already have them all.

The schema can't express a few rules, and the exporter has to guarantee them:
- the trophy shelf is ordered by titles, then runner-ups (both descending), then name
- `standings` has one entry per Franchise and is ordered by `rank`
- the Champion in the league summary matches the latest Season's Podium

## Using it

**Python** (pipeline tests, exporter):

```python
from washingwood.contract import validate, ContractError
validate(doc, "season")  # kinds: "league", "trophyShelf", "season"
```

`ContractError.errors` lists every violation as `"/json/pointer: message"`.

**JavaScript** (site tests), with [Ajv](https://ajv.js.org/) 2020:

```js
import Ajv2020 from "ajv/dist/2020";
import schema from "../contract/site-data.schema.json";

const ajv = new Ajv2020({ allErrors: true });
ajv.addSchema(schema);
const validateSeason = ajv.getSchema(`${schema.$id}#/$defs/season`);
if (!validateSeason(doc)) throw new Error(JSON.stringify(validateSeason.errors));
```

## Tests

`tests/test_site_contract.py` checks three things:
- `validate()` accepts and rejects the right documents
- the examples validate and agree with each other
- every schema field is documented
