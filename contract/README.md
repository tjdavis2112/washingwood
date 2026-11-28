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
| `examples/transactions.json` | Example Transactions: invented trades (a tie, a Week-1 trade, a Stint cut short by a later trade, a Margin tie at the 5th Fleeced place; 2018 has none, for the empty-Season line) and Pickups (a re-add, tied points, rows cut from the top 10) scored by the plain-Python reference `tests/transactions_examples.py` (re-run it after changing them) |
| `examples/hall-of-fame.json` | Example Hall of Fame: invented Player seasons in all three lanes (a traded Player, a tie on starter points, one exactly at each bar and one just under it, one who never started but overachieved, a Player with two Pickups, a Waiver legend with no Season points, two-lane Inductees whose lanes name the same Owner and different Owners; Inductees in both Seasons, one on the former Owner; card backs with a standout best Week, two-week playoff rounds, a Champion, a runner-up and Owners who missed the playoffs, and two Owner's notes) inducted by the plain-Python reference `tests/hall_of_fame_examples.py` (re-run it after changing them or a bar) |
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
| Transactions | `#/$defs/transactions` | `transactions.json` |
| Hall of Fame | `#/$defs/hallOfFame` | `hall-of-fame.json` |

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
- `record-book.json` `season.luckiest` / `unluckiest` rank Franchise-Seasons by Luck index: actual wins minus Expected wins (all-play win % x games; all-play counts regular-season Weeks only, 1 per Franchise outscored and 1/2 per tie, divided by the other Franchises that Week). Luck is rounded to one decimal from the unrounded Expected wins; `allTime.luck` sums the Seasons. Both are null without lineups
- `record-book.json` `streaks` lists hold the 10 longest runs of regular-season wins and of losses per kind, carried across Seasons (a sat-out Season doesn't break one, a tie ends it); equal lengths go to the earlier start Season, then Week, then Owner name. `active` means it runs through the latest Season's last regular-season game. `allTime` carries each Owner's `longestWinStreak` and `longestLossStreak`
- `record-book.json` `week` lists hold the top 10 sides of Counted Matchups (a tied Matchup is neither a win nor a loss); ties go to the earlier Season, then Week, then Owner name. Bench points count BE slots only (IR excluded, a Player who didn't play counts 0); Season and All-time Bench points sum regular-season Weeks and are null without lineups
- `record-book.json` `season` lists hold the top 10 Franchise-Seasons, regular season only; points rank per game (`pointsPerGame`, `pointsAgainstPerGame`), win % counts a tie as half a win, and ties go to the earlier Season, then Owner name. `allTime` has one row per Owner, former Owners included, ordered by wins (descending), then name
- `record-book.json` `lastPlace.seasons` is newest first, one row per Season, matching each Season's `lastPlace`; the tally is ordered by count (descending), then name
- `transactions.json` marks exactly the 5 largest Margins `fleeced` (ties: Season, Week, winner's name; never a tie, so fewer than 5 only when fewer trades were won); `activity` has every Owner, most trades + Pickups first, then name
- `transactions.json` `tradeRecords` has one row per Owner who traded (won + lost + tied = their trades in `trades`; net points summed over their trades, so all rows sum to 0), highest net points first; `ownerPickups` has every Owner, by name, with their top 5 Pickups. Owner pages take their trades from `trades` by a side's Owner slug
- `transactions.json` `seasonPickups` has one entry per Season, newest first, each that Season's top 10 Pickups ordered like `pickups`; Season pages take their trades from `trades` by `year`
- `transactions.json` decides trades and ranks Pickups by Value added (`total`, `value`); raw starter points (`rawTotal`, `points`) ride along for reference. Each start's Value added uses that Season's Replacement points per start, the same Replacement level the Draft section uses
- `transactions.json` `pickups` are the top 10 Pickups by Value added (ties: Season, Week, Owner name, Player name); a Player dropped and re-added is two Pickups whose Stints never share a Week
- `transactions.json` `trades` are newest Season first, then newest Week, then the first side's Owner name; each side's total is the sum of its Players' points, the winner comes first, and `margin` is the difference of the two totals. Season pages and Owner pages get their trades by filtering this document at site build time (by `year`, or by a side's Owner slug), so trades have one source
- `hall-of-fame.json` `inductees` are one per Player season that clears at least one Induction bar (`washingwood.hall_of_fame`; ADR-0009): **dominant**, Points above replacement at or above `PAR_BAR`, among Players on a roster at some point that Season who started at least once, credited to the Owner of the Franchise the Player scored the most starter points for (a tie goes to the earlier acquisition: the Franchise whose lineups had him first); **overachiever**, a Pick's Points over expected at or above `POE_BAR`, credited to the drafting Franchise's Owner; **waiver_legend**, the Player season's best Pickup's Value added over its Stint at or above `PICKUP_BAR`, credited to the acquiring Franchise's Owner (a tie goes to the earlier Pickup). `lanes` lists every lane cleared in that credit order, each with its own Owner; the Inductee's `owner` and `teamName` are the first lane's. `points` and `positionalFinish` are null when the Archive has no Season points for the Player (only a Waiver legend can be; he sorts last in his Season). Newest Season first, then highest Points above replacement, then Player name. Bars are fixed, never ranks, so a later Season never removes an Inductee (Points over expected can drift, ADR-0009)
- An Inductee's `moments` (the card back) are all for the credited Owner's Franchise: `bestWeek`, his highest starter score in a Counted Matchup (so never a two-week round; a tie goes to the earlier Week) with its opponent and result, null if he never started there; `playoffPoints`, his starter points over every Week of the championship-bracket Matchups it played (byes aren't played), 0 if he started none, null if it played none; `championshipPoints`, the same for the championship game, null if it wasn't in it; `finish` (`finalRank`, `playoffSeed`, `madePlayoffs`); `weeksStarted`. The other lanes' Owners are in `lanes`. `ownerNote` is the Owner's note from the private `hall_of_fame.yaml` (`--hall-of-fame`), null until written
- `hall-of-fame.json` is the one source for Inductees: Season pages take theirs by filtering `inductees` by `year`, and Owner pages by the credited `owner.slug`, at site build time. Season and Owner documents carry no copy
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
)  # kinds: "league", "trophyShelf", "ownerIndex", "owner", "season", "draft", "matchups", "rivalry", "boxScores", "recordBook", "transactions", "hallOfFame"
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
