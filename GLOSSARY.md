# League History

The permanent record of one fantasy football league across every season and platform it has used.

## Identity

**League**:
The ongoing competition among a group of **Owners**, across all **Seasons** and platforms.
_Avoid_: Group

**Owner**:
A real person who runs a **Franchise** in one or more **Seasons**. Survives team renames and platform switches.
_Avoid_: Manager, user, member, team

**Franchise**:
One team in one **Season**, linked to its **Owners** through `franchise_owners`. A new Franchise exists every Season, even for the same Owner.
_Avoid_: Team (when you mean the cross-season entity), roster

**Player**:
An NFL player, identified across platforms by `player_external_ids`.

## Seasons and data

**Season**:
One year of the **League**, with its own rules, **Scoring format** and **Data tier**.
_Avoid_: Year (in code), league year

**Data tier**:
How much detail the platform still returns for a **Season**: `full` (2019+), `partial` (2018), or `archival` (≤2017: standings, matchup scores, draft, settings only).

**Scoring format**:
A **Season**'s headline scoring rule set (PPR, Half PPR, Standard, plus TE premium). Records are only comparable within one format.

**Raw response**:
One untouched platform API response, saved to the **Archive** and never edited.

**Archive**:
The on-disk store of **Raw responses** (`archive/<league>/<year>/`) and its `manifest.jsonl`. Every other layer is rebuilt from it.

## Games

**Week**:
One NFL week. ESPN calls it `scoringPeriodId`.
_Avoid_: Scoring period (outside ESPN-specific code)

**Matchup period**:
The unit a **Matchup** is scored over. Usually one **Week**; playoff periods can span two.

**Matchup**:
Two **Franchises** facing off over one **Matchup period**, or one Franchise on a bye.
_Avoid_: Game, box score (a box score is the detailed view of a Matchup)

**Lineup entry**:
One **Player** on one **Franchise** in one **Week**, in a slot. Starter if the slot is not `BE` or `IR`.

**Podium**:
A **Season**'s 1st, 2nd and 3rd place **Franchises**. Shown for every Season, archival included.

## Analysis

**Value over slot**:
A draft pick's season points minus the average for that overall pick across all **Seasons**.

**All-play record**:
A **Franchise**'s record if it had played every other Franchise every **Week**.

**Luck index**:
The gap between a **Franchise**'s actual record and its **All-play record**.

**Acquisition impact**:
Points a **Player** scored as a starter for the **Franchise** that acquired them, from the acquisition **Week** to the end of the **Season**.
