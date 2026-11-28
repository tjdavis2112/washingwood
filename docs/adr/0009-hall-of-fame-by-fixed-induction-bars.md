# Hall of Fame induction is computed from fixed Induction bars, never re-ranked

A **Player** season enters the **Hall of Fame** when it clears any one of three fixed **Induction bars**: Points above replacement (**Dominant**), Points over expected (**Overachiever**) or a Pickup's Value added (**Waiver legend**). Each bar is a constant in code, not a rank. So adding a Season can induct new Player seasons but never removes an earlier one, and nothing about who was inducted has to be stored. The bars are set so only a few Player seasons clear them each Season; zero is allowed.

The bars are calibrated once against the real **Archive** with a local-only report. The chosen values are recorded here, and changing them needs a new ADR, because that is the one way an **Inductee** can leave the Hall.

| Bar | Lane | Value |
|---|---|---|
| `PAR_BAR` | Dominant | TBD (set in #74) |
| `POE_BAR` | Overachiever | TBD |
| `PICKUP_BAR` | Waiver legend | TBD |

## Considered Options

- **Curated by hand**: the league's real legends, but someone has to maintain a list, and that list would hold league data in the private repo. Rejected for selection. Only the **Owner's note** is hand-written.
- **All-time top N per lane**: always a tidy list, but a great new Season pushes an older Inductee out. Rejected.
- **The top Player season per lane in each Season**: the Hall only grows, but every Season inducts someone even in a weak year. Rejected.
- **Store inductions once made**: makes inductions permanent even under a ranking, but adds state the rebuild-from-raw model avoids (ADR-0001). Rejected.

## Consequences

- Points over expected pools every Season (ADR-0008), so a later Season can nudge an Overachiever's value across its bar. That's accepted as rare. If it happens, it shows up as a changed Inductee count in the report.
- Inductees are derived, so the unused `core.hall_of_fame` columns (`franchise_id`, `inducted_year`) go. That table holds only Owner's notes, loaded from `hall_of_fame.yaml` in `washingwood-archive` (ADR-0007), keyed by Season and ESPN player ID like `owners.yaml`. A note that matches no Inductee fails the build.
- One bar per lane is used across **Scoring formats**. All three measures are taken against their own Season's **Replacement level**, so that's fair enough to compare. The calibration report shows counts per Season, so any skew is visible. Cards show the Scoring format.
