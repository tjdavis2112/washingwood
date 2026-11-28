# Site-data contract

The site-data contract is the interface between the **pipeline** (Python: archive → Postgres → JSON) and the **site** (Astro). The pipeline's exporter writes these JSON documents and the site renders only from them. Both sides test against the same schema, so they can't drift apart without a test failing.

## Files

| Path | What it is |
| --- | --- |
| `site-data.schema.json` | The JSON Schema (draft 2020-12). Every field has a `description`, so this file is the field reference. |
| `examples/league.json` | Example league summary |
| `examples/trophy-shelf.json` | Example trophy shelf |
| `examples/owners.json`, `examples/owners/<slug>.json` | Example Owner index and Owner documents, derived from the other examples by `tests/owner_examples.py` (re-run it after changing them) |
| `examples/matchups.json`, `examples/rivalries/<a>-vs-<b>.json` | Example Matchups document and Rivalry documents, derived from the Season examples and `owners.json` by `tests/matchup_examples.py` (re-run it after changing them) |
| `examples/box-scores/<year>.json` | Example Box scores, invented (deterministically) from the Season examples by `tests/box_score_examples.py`: lineups use each Owner's example draft, and starters add up to each score (re-run it after changing the Season examples) |
| `examples/record-book.json` | Example Record Book, derived from the Season examples by `tests/record_book_examples.py` (re-run it after changing them) |
| `examples/draft.json` | Example Draft history, derived from the Season examples by `tests/draft_examples.py` (re-run it after changing them) |
| `examples/seasons/2018.json` | Example 10-team Season: 4 playoff teams, two-week playoff rounds, a tie, one manual score adjustment, a Last place who wins a consolation Matchup, and an offline Draft with three Picks not recorded |
| `examples/seasons/2020.json` | Example 12-team Season: 6 playoff teams, first-round byes, the Third-place game, a 5th-place Matchup, and a snake Draft |

Every Owner and team name in `examples/` is invented (ADR-0007). The real exported data goes to the gitignored `export/` folder and is never committed.

## Document kinds

The schema has one entry point per document under `$defs`:

| Kind | Entry point | Exported as |
| --- | --- | --- |
| League summary | `#/$defs/league` | `league.json` |
| Trophy shelf | `#/$defs/trophyShelf` | `trophy-shelf.json` |
| Owner index | `#/$defs/ownerIndex` | `owners.json` |
| Owner | `#/$defs/owner` | `owners/<slug>.json` |
| Season | `#/$defs/season` | `seasons/<year>.json` |
| Draft history | `#/$defs/draft` | `draft.json` |
| Matchups | `#/$defs/matchups` | `matchups.json` |
| Rivalry | `#/$defs/rivalry` | `rivalries/<a>-vs-<b>.json` |
| Box scores | `#/$defs/boxScores` | `box-scores/<year>.json` |
| Record Book | `#/$defs/recordBook` | `record-book.json` |

## Conventions

- **Owners** are always `{"slug", "name"}`. The slug is stable and URL-safe, and is never an ESPN ID (ADR-0002). A given slug carries the same name in every document.
- **Unknown fields are rejected** (`additionalProperties: false` everywhere). To add a field, change the schema first.
- **Matchups** share one rule set:
  - A bye has `away: null`, `winner: null` and `isTie: false`. In weekly results its home score is what ESPN recorded for that Week; in the bracket it's null (no game was played).
  - Otherwise both scores are numbers. A tie has `winner: null`, and anything else has `winner` set to `"home"` or `"away"`.
- **Two-week rounds** list both Weeks in `weeks`, and their scores are combined.
- **Last place** is the highest `playoffSeed`, not the bottom of `standings`.
- **`punishment`** is always present and is `null` in v1.
- **Draft** Picks are in overall order and every Pick has an Owner. `player` is `null` when no Player was recorded, and `nflTeam` is `null` for a free agent. Platform IDs (member, player) never appear.
- **Every Season section is required.** The pipeline exports them all (#7 to #10).

The schema can't express a few rules, and the exporter has to guarantee them:
- the trophy shelf and the Owner index are ordered by titles, then runner-ups (both descending), then name
- every Owner in the index has an Owner document, named by its slug
- `matchups.json` championships are newest first and match each Season's bracket final
- `box-scores/<year>.json` exists for every Season with lineups and holds every played Matchup; each side's starters add up to its score
- every pair in `rivalryGrid.records` has a Rivalry document (slugs in alphabetical order), and its records match both Owners' `headToHead` rows
- `record-book.json` `streaks` lists hold the 10 longest runs of regular-season wins and of losses per kind, carried across Seasons (a sat-out Season doesn't break one, a tie ends it); equal lengths go to the earlier start Season, then Week, then Owner name. `active` means it runs through the latest Season's last regular-season game. `allTime` carries each Owner's `longestWinStreak` and `longestLossStreak`
- `record-book.json` `week` lists hold the top 10 sides of Counted Matchups (a tied Matchup is neither a win nor a loss); ties go to the earlier Season, then Week, then Owner name. Bench points count BE slots only (IR excluded, a Player who didn't play counts 0); Season and All-time Bench points sum regular-season Weeks and are null without lineups
- `record-book.json` `season` lists hold the top 10 Franchise-Seasons, regular season only; points rank per game (`pointsPerGame`, `pointsAgainstPerGame`), win % counts a tie as half a win, and ties go to the earlier Season, then Owner name. `allTime` has one row per Owner, former Owners included, ordered by wins (descending), then name
- `record-book.json` `lastPlace.seasons` is newest first, one row per Season, matching each Season's `lastPlace`; the tally is ordered by count (descending), then name
- `draft.json` lists every Season newest first, and each `firstRound` is that Season's round-1 Picks in order
- `standings` has one entry per Franchise and is ordered by `rank`
- the Champion in the league summary matches the latest Season's Podium
- `draft.picks` holds teamCount x rounds Picks numbered 1..N in snake order, and `draft.order` lists every Franchise once by Draft slot

## Using it

**Python** (pipeline tests, exporter):

```python
from washingwood.contract import validate, ContractError

validate(
    doc, "season"
)  # kinds: "league", "trophyShelf", "ownerIndex", "owner", "season", "draft", "matchups", "rivalry", "boxScores", "recordBook"
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
