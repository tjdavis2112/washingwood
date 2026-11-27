# Draft grades use Points over expected; Value over slot only ranks Steals

Draft grades used to be the sum of **Value over slot**, a rank gap within a position. Rank gaps are bounded by how early a Pick was made, so an early Pick that becomes a league winner could barely score (a 3rd-round WR who finished WR2 scored about +11), while a late Pick that became a mid-level starter scored +40 to +50. The all-time best Picks were all from rounds 14 to 18. "Good pick" means two different things: outplaying where you went, and producing a lot for what you spent. One number can't rank both.

We split them. **Points over expected** (Points above **Replacement level**, floored at 0, minus the mean for that round across every Season) is the per-Pick value on boards and Owner pages, ranks the **Hits** and **Busts**, and adds up to the **Draft grade**. **Value over slot** stays, unchanged, and ranks only the **Steals**.

## Considered Options

- **Keep Value over slot for everything**: it's simple, but it's what caused the problem.
- **Points minus the points of the drafted Player at the same positional slot**: late slots have a par near 0, so every late hit topped the list. Rejected.
- **A 50/50 blend of both, put on the same scale**: the lists look balanced, but the number has no unit and is hard to explain. Rejected.
- **Expected value from a ±5-pick window instead of the round**: within a few places of the round version on real data, and harder to explain ("what a 3rd-rounder usually returns"). Rejected.

## Consequences

- The expectation for a round pools every Season, so adding a Season moves earlier Seasons' values and grades a little. That's accepted: the comparison is against this league's history.
- Replacement level counts each FLEX as half an RB and half a WR, and ignores TE in the FLEX. That's an approximation, recorded in the GLOSSARY.
- The Season document carries each position's Replacement level, so a page can explain it and the invented examples can be checked without undrafted Players.
- `draft.json` lists `steals`, `hits` and `busts` instead of `bestPicks` and `worstPicks`.
