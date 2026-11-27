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

**Replacement level**:
Per **Season** and position, the last starter-quality finish: team count × that position's starting slots, each FLEX counting as half an RB and half a WR, rounded up (a position with no starting slot counts one per team). Replacement points are the **Season points** of the **Player** at that **Positional finish** (on a tie that skips it, the nearest finish above; with fewer Players, the last one). 12 teams with 2 RB and 2 FLEX: RB36.

**Points above replacement**:
A drafted **Player**'s **Season points** minus their position's Replacement points that Season, never below 0 (anyone below replacement was waiver-wire level).

**Points over expected**:
A **Pick**'s **Points above replacement** minus what a Pick in that round usually returns: the mean Points above replacement of every recorded Pick in that round, across every **Season**. Rounded to whole points. Positive beat its round, negative fell short. It ranks the **Hits** and **Busts** and adds up to the **Draft grade**. Picks with no Player recorded are left out.
_Avoid_: Draft value (unqualified), VOR

**Value over slot**:
A **Pick**'s order among that **Season**'s Picks at its position (1 = the first QB taken), minus its finish by **Season points** among the drafted Players at that position (ties share the better finish). The 8th QB taken who finishes as the 2nd-best drafted QB scores +6. Rank-based, so it rewards late-round finds and caps early ones: it ranks the **Steals** only, not the Draft grade. Compared within a position and within one Season. Picks with no Player recorded are left out.
_Avoid_: Draft value (unqualified)

**Draft grade**:
The sum of a **Franchise**'s **Points over expected** in one **Season**, ranked within that Season. No letter grades.

**Hit** / **Bust**:
The all-time 10 **Picks** with the highest / lowest **Points over expected**. A Hit can come from any round; Busts are mostly early Picks that fell apart.

**Steal**:
One of the all-time 10 **Picks** with the highest **Value over slot**: a Player who outplayed where they went.

**Record Book**:
The site's cross-**Season** records: Week, Season and all-time leaderboards, **Streaks**, **Luck index**, **Bench points** and **Last place** history. Single-game extremes (blowouts, closest games, highest and lowest scores, upsets) stay on the Matchups leaderboards.

**Points per game**:
A **Franchise**'s regular-season points for divided by its regular-season games, to two decimals. Season records rank points by it, so 13-game and 14-game Seasons compare fairly.

**Bench points**:
The points a **Franchise**'s bench **Lineup entries** scored in a **Week**. IR slots don't count, and a **Player** who didn't play counts 0. Not adjusted for bench size, and not a judgement of whether those Players could have started.

**Streak**:
An **Owner**'s run of consecutive regular-season wins, or of losses, in order across **Seasons**. A Season the Owner sat out doesn't break it, a tie ends it, and playoff games don't count. A Streak still running at the end of the latest Season is **active**.

**All-play record**:
A **Franchise**'s record if it had played every other Franchise every regular-season **Week**. Each Week it gets a win for each Franchise it outscored and half a win for each tie. All-play win % is those wins divided by the number of other Franchises that Week (9 or 11), averaged over the Season.

**Expected wins**:
A **Franchise**'s all-play win % times its regular-season games: the wins an average schedule would have given it.

**Luck index**:
A **Franchise**'s actual regular-season wins minus its **Expected wins**, to one decimal. Positive is lucky. An **Owner**'s all-time Luck index is the sum of their Seasons.

**Acquisition impact**:
Points a **Player** scored as a starter for the **Franchise** that acquired them, from the acquisition **Week** to the end of the **Season**.
