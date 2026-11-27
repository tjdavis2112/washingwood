# Washingwood

Washingwood is our fantasy football league. This glossary covers the language of its permanent history, from the 2018 **Season** onward.

## Identity

**League**:
Washingwood: the ongoing competition among its **Owners**, across all **Seasons**. Its recorded history starts in 2018. Ten teams through 2019, twelve from 2020.
_Avoid_: Group

**Owner**:
A real person who runs a **Franchise** in one or more **Seasons**. Survives team renames, account changes and gaps. An owner who has left still has their history.
_Avoid_: Manager, user, member, team

**Current team name**:
The team name of an **Owner**'s most recent **Franchise**. Used to label the Owner across all Seasons.

**Franchise**:
One team in one **Season**, run by exactly one **Owner**. Washingwood has no co-owners. Each Season has a new Franchise, even for the same Owner.
_Avoid_: Team (when you mean the cross-season entity), roster

**Player**:
An NFL player. The same person whichever platform reports them.

## Seasons and data

**Season**:
One year of the **League**, with its own rules, **Scoring format** and **Data tier**. A Season enters the history only after it ends.
_Avoid_: Year (in code), league year

**Data tier**:
How much detail survives for a **Season**: **full** (lineups, player stats, transactions) or **partial** (league-level results, some detail missing).

**Scoring format**:
A **Season**'s headline scoring rule set (PPR, Half PPR, Standard, plus TE premium). Records are only comparable within one format.

**Raw response**:
One untouched platform API response, kept exactly as received.

**Archive**:
The full set of **Raw responses**. Everything else in the history is rebuilt from it.

## Games

**Week**:
One NFL week.
_Avoid_: Scoring period

**Matchup period**:
The unit a **Matchup** is scored over. Usually one **Week**. Playoff periods can span two.

**Matchup**:
Two **Franchises** facing off over one **Matchup period**, or one Franchise on a bye.
_Avoid_: Game, box score (a box score is the detailed view of a Matchup)

**Lineup entry**:
One **Player** on one **Franchise** in one **Week**, in a lineup slot. A starter unless the slot is bench or IR.

**Box score**:
The detailed view of one played **Matchup**: each side's **Lineup entries** with points and projections, and the totals. A two-week round shows each **Week**'s lineup.

**Projected score**:
The sum of a **Franchise**'s starters' platform projections for a **Week**, as the platform projected them before the games.

**Champion**:
The **Franchise** that wins a **Season**'s championship **Matchup**. Its **Owner** earns a title.
_Avoid_: Winner (ambiguous with a weekly Matchup winner)

**Third-place game**:
The playoff **Matchup** between the two semifinal losers. Its winner takes 3rd.

**Playoff record**:
An **Owner**'s wins, losses and ties in championship-bracket **Matchups** they actually played: quarterfinals, semifinals and the championship. A two-week round counts as one game. Byes, the **Third-place game** and consolation Matchups don't count.
_Avoid_: Postseason record

**Playoff appearance**:
A **Season** in which a **Franchise**'s seed is within that Season's playoff field. A first-round bye counts.

**Counted Matchup**:
A regular-season **Matchup**, or a championship-bracket Matchup actually played, that spans a single **Week**. The set Matchup leaderboards draw from. Byes, the **Third-place game**, consolation Matchups and two-week rounds aren't counted.

**Margin**:
The winner's score minus the loser's in a played **Matchup**.

**Playoff upset**:
A championship-bracket **Matchup** won by the worse seed.

**Projection upset**:
A **Counted Matchup** won by the **Franchise** with the lower **Projected score**. Ranked by how far behind the winner was projected.

**Rivalry**:
Two **Owners**' head-to-head history: their records against each other (regular season and **Playoff record** rules) and every Matchup they've played, consolation games included but not counted.

**Podium**:
A **Season**'s **Champion**, runner-up and **Third-place game** winner.

**Last place**:
The **Franchise** with the worst regular-season standing in a **Season**. Playoff and consolation results don't change it. Its **Owner** serves that Season's **Punishment**.
_Avoid_: Loser, toilet bowl winner

**Punishment**:
The penalty the **Last place** **Owner** serves for a **Season**. Chosen fresh each Season, with its own title, description and picture.

## Draft

**Draft**:
A **Season**'s player draft: a snake draft (2019 onward) or, in 2018, an offline draft entered by hand.

**Pick**:
One selection in a **Draft**: its overall number, round and pick within the round, the **Franchise** that made it, and the **Player** taken. A Pick can have no Player recorded (13 late 2018 Picks).
_Avoid_: Selection, draft slot (a slot is the position in the order)

**Draft slot**:
A **Franchise**'s position in round 1 of the **Draft** order. The order reverses each round.

**Season points**:
A **Player**'s fantasy points for a **Season** under that Season's scoring: ESPN's season total, covering the whole NFL regular season. From 2021 that includes NFL week 18, which is after the fantasy season.

**Positional finish**:
A **Player**'s rank by **Season points** among every Player at their position that **Season** (e.g. RB3).

## Analysis

**Value over slot**:
A **Pick**'s order among that **Season**'s Picks at its position (1 = the first QB taken), minus its finish by **Season points** among the drafted Players at that position (ties share the better finish). The 8th QB taken who finishes as the 2nd-best drafted QB scores +6. Positive is a steal, negative a bust. Compared within a position, so one-per-team positions (QB, K, D/ST) aren't steals by default, and within one Season, so it compares across Scoring formats and team counts. Picks with no Player recorded are left out.
_Avoid_: Draft value (unqualified)

**Draft grade**:
The sum of a **Franchise**'s **Value over slot** in one **Season**, ranked within that Season. No letter grades.

**All-play record**:
A **Franchise**'s record if it had played every other Franchise every **Week**.

**Luck index**:
The gap between a **Franchise**'s actual record and its **All-play record**.

**Acquisition impact**:
Points a **Player** scored as a starter for the **Franchise** that acquired them, from the acquisition **Week** to the end of the **Season**.
