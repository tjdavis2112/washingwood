"""Synthetic, ESPN-shaped fixture archives for Seam 1 tests.

Shapes follow docs/research/espn-api.md (§1 settings, §2 teams, §3 matchups). Every Owner,
member ID and team name is invented (ADR-0007). Nothing here derives from the real archive.

Two Season shapes, matching the real league's two eras (espn-api.md §9):
- Season2018Style: 10 teams, 13 regular-season periods, 4 playoff teams, two-week playoff periods.
- Season2020Style: 12 teams, 14 regular-season periods, 6 playoff teams, byes, a 5th-place game.

Playoff rule, so expected results are easy to reason about: the higher seed wins every
playoff Matchup unless the other team is listed in `upsets`. Regular-season records are set
from the seed: seed s finishes (regular periods - s) wins and s losses, with points for
1500 - s (plus any manual adjustment) and points against 1400 + s.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

LEAGUE_ID = "999001"  # invented
WB, WCL, LCL = "WINNERS_BRACKET", "WINNERS_CONSOLATION_LADDER", "LOSERS_CONSOLATION_LADDER"
# ESPN records what a team on a playoff bye scored that Week (the real archive has 62-204)
BYE_POINTS = 110.25

# Headline scoring items (statId -> base points), espn-api.md §5 statId
BASE_SCORING = {3: 0.04, 4: 4.0, 20: -2.0, 24: 0.1, 25: 6.0, 42: 0.1, 43: 6.0, 72: -2.0}
# lineupSlotId -> count (espn-api.md §5): QB, RB x2, WR x2, TE, FLEX, D/ST, K, BE x7, IR 0
LINEUP_SLOTS = {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "16": 1, "17": 1, "20": 7, "21": 0}

# Draft: 3 rounds keeps fixtures small. Fixture Players are a pure function of the overall pick, so the
# same pick number drafts the same Player in every Season (one Player across Seasons).
DRAFT_ROUNDS = 3
# defaultPositionId by (overall - 1) % 6: RB, WR, QB, TE, D/ST, K (espn-api.md §5)
POSITION_CYCLE = [2, 3, 1, 4, 16, 5]
# proTeamId (espn-api.md §5): ATL, BUF, CHI, ..., HOU; 0 = free agent, used for the undrafted Player
PRO_TEAMS = [i for i in range(1, 35) if i not in (31, 32)]
UNDRAFTED_PLAYER_ID = 9999


def fixture_player_id(overall: int) -> int:
    """ESPN-style ID: D/ST IDs are negative (-16000 - proTeamId), everyone else positive."""
    if POSITION_CYCLE[(overall - 1) % 6] == 16:
        return -16000 - PRO_TEAMS[(overall - 1) % len(PRO_TEAMS)]
    return 5000 + overall


def _overall_of(pid: int) -> int | None:
    if pid == UNDRAFTED_PLAYER_ID:
        return None
    if pid < 0:
        return next(o for o in range(1, 400) if fixture_player_id(o) == pid)
    return pid - 5000


def fixture_player_position(pid: int) -> int:
    overall = _overall_of(pid)
    return 3 if overall is None else POSITION_CYCLE[(overall - 1) % 6]


def fixture_player_pro_team(pid: int) -> int:
    overall = _overall_of(pid)
    return 0 if overall is None else PRO_TEAMS[(overall - 1) % len(PRO_TEAMS)]


def fixture_player_points(pid: int) -> float:
    """Default Season points fall with the overall pick, so every Pick's Value over slot is 0."""
    overall = _overall_of(pid)
    return 50.0 if overall is None else 400.0 - 3 * overall


def fixture_player_name(pid: int) -> str:
    overall = _overall_of(pid)
    if overall is None:
        return "Undrafted Fixture"
    if fixture_player_position(pid) == 16:
        return f"Team{fixture_player_pro_team(pid)} D/ST"
    return f"Fixture Player {overall:03d}"


STARTERS = [(0, 1), (2, 2), (2, 2), (4, 3), (4, 3), (6, 4), (23, 2), (16, 16), (17, 5)]  # (lineupSlotId, position)
BENCH = [(20, 2), (20, 3), (20, 3), (20, 4), (20, 1), (20, 2), (21, 3)]
LINEUP = STARTERS + BENCH  # index = lineup slot index; 8 is the K, who absorbs point overrides


def lineup_player_id(team_id: int, index: int) -> int:
    """The Player who starts the Season in a team's lineup slot `index`. D/ST IDs are negative, and kept
    clear of the drafted D/STs' (-16000 - proTeamId) so a Week-1 roster diff sees no false moves."""
    return -16100 - team_id if LINEUP[index][1] == 16 else 70000 + team_id * 100 + index


def lineup_player(pid: int) -> tuple[str, int, int]:
    """(fullName, defaultPositionId, proTeamId) of any Player who appears in a fixture lineup."""
    if 70000 <= pid < 80000:
        team_id, index = divmod(pid - 70000, 100)
        return f"Lineup {team_id}-{index:02d}", LINEUP[index][1], 1 + index
    if 60000 <= pid < 70000:  # a free agent (free_agent_id)
        kind, n = divmod(pid - 60000, 1000)
        return f"Free Agent {n:03d}", kind or 2, 9
    if -16200 < pid <= -16100:  # a team's own D/ST
        return f"Team{-16100 - pid} D/ST", 16, 8
    return fixture_player_name(pid), fixture_player_position(pid), fixture_player_pro_team(pid)


@dataclass
class FixtureTrade:
    """One trade in mTransactions2 shape (espn-api.md §7) and on the weekly rosters.

    Team `a` accepts (TRADE_ACCEPT.teamId); `b` proposed. The two teams swap whoever holds each of
    `slots` (lineup slot indices) from the effective Week (week + lag) on. With `draft_round` set, the
    trade happens before roster_w01: each team's Pick from that round moves into the other team's slot
    `slots[0]` instead (the Week-1 case, diffed against the draft roster).
    """

    week: int  # TRADE_ACCEPT scoringPeriodId
    a: str
    b: str
    slots: tuple[int, ...] = (1,)
    # b's slots, when they differ from a's: a's slots[i] player goes to b's b_slots[i], and back
    b_slots: tuple[int, ...] | None = None
    lag: int = 0  # 1 = the move shows on roster_w(week + 1), as after a review window
    legs: bool = False  # 2018 style: TRADE items on TRADE_ACCEPT, no relatedTransactionId
    team_actions: bool = False  # list both teams in teamActions (else the partner comes from the diff)
    second_accept: bool = False  # a 2nd TRADE_ACCEPT (EXECUTED) carrying the legs, as 2020/2022/2024 have
    veto: str | None = None  # "commissioner" (the trade dies: nothing moves) or "minority" (it stands)
    draft_round: int | None = None
    moves: bool = True  # False: the rows say a trade happened, but no roster shows it

    @property
    def effective_week(self) -> int:
        return self.week + self.lag

    @property
    def executes(self) -> bool:
        return self.veto != "commissioner"


@dataclass
class FixtureMove:
    """A waiver claim, free-agent add or standalone drop: one mTransactions2 row (espn-api.md §7).

    An executed row changes `team`'s lineup slot `slot` from `week` on: `add` (a free agent) takes the
    slot, and with `drop` whoever held it is dropped in the same row. A drop-only row (`add` None) puts
    a placeholder in the slot. Rows that didn't execute change nothing.
    """

    week: int  # scoringPeriodId
    team: str  # receiving team: items[].toTeamId
    slot: int = 1
    add: int | None = None
    drop: bool = True
    type: str = "WAIVER"  # WAIVER, FREEAGENT, or ROSTER (a 2020+ standalone drop)
    status: str = "EXECUTED"  # also CANCELED, PENDING, FAILED_INVALIDPLAYERSOURCE, ...
    execution_type: str | None = None  # default: PROCESS for WAIVER, else EXECUTE; 2018 cancels use CANCEL
    row_team: str | None = None  # top-level teamId, when it differs from the item's (2018)

    @property
    def executes(self) -> bool:
        return self.status == "EXECUTED"


# pool_points_by_position that makes every position's Replacement points 0, so Value added = raw points
NO_REPLACEMENT = {position: 0.0 for position in (1, 2, 3, 4, 5, 16)}


def free_agent_id(n: int, position: int = 2) -> int:
    """An invented free agent, in no lineup until someone adds them. RB by default; position is a
    defaultPositionId (1 QB, 3 WR, 4 TE, 5 K) and n stays under 1000."""
    return 60000 + n if position == 2 else 60000 + position * 1000 + n


@dataclass
class Team:
    """One Franchise in a fixture Season."""

    key: str  # test handle, e.g. "quinn"
    name: str  # team name that Season
    member: str  # invented ESPN member ID ("{...}" form)
    extra_members: tuple[str, ...] = ()  # more ESPN accounts listed on the team (the same Owner's)


@dataclass
class FixtureSeason:
    """Shared ESPN-document building. Subclasses set the shape and play out the Season."""

    year: int
    teams_by_seed: list[Team]  # index 0 = seed 1
    upsets: set[str] = field(default_factory=set)
    league_name: str = "Example Fantasy League"
    # Reception scoring as in 2025: base 0, per-position overrides, TE gets 1.5 (a 0.5 TE premium)
    te_premium: bool = False
    # Manual score adjustments by team key: in points for, not in Matchup scores (espn-api.md §3)
    adjustments: dict[str, float] = field(default_factory=dict)
    # Regular-season period whose first Matchup ends in a tie (both sides 110.0, winner TIE)
    tie_period: int | None = None
    # Draft (espn-api.md §6): "SNAKE" or "OFFLINE". Overall picks listed in unrecorded_picks have
    # playerId -1 and lineupSlotId -1, as in the real 2018 offline draft.
    draft_type: str = "SNAKE"
    unrecorded_picks: set[int] = field(default_factory=set)
    # playerId -> fullName, to rename a fixture Player in one Season
    player_names: dict[int, str] = field(default_factory=dict)
    # Overall picks to leave out of draftDetail.picks (to break the pick count)
    missing_picks: set[int] = field(default_factory=set)
    # playerIds to leave out of players.json
    unlisted_players: set[int] = field(default_factory=set)
    # Season points (player_pool.json season total) by playerId; default fixture_player_points(). A playerId
    # that isn't drafted (a lineup Player or a free agent) is added to the pool with these Season points.
    player_points: dict[int, float] = field(default_factory=dict)
    # Season points for every pool Player at a position (defaultPositionId -> points), unless player_points
    # names them. Every Player at a position scoring the same fixes that position's Replacement points.
    pool_points_by_position: dict[int, float] = field(default_factory=dict)
    # playerIds whose season-total row is left out of player_pool.json
    pool_without_points: set[int] = field(default_factory=set)
    # Extra undrafted pool Players: playerId -> (defaultPositionId, points)
    undrafted: dict[int, tuple[int, float]] = field(default_factory=dict)
    # Set a Matchup's scores: (matchup period, index of the Matchup within that period in schedule
    # order) -> (home points, away points). The winner follows the scores, so keep the original winner
    # for playoff Matchups or the bracket checks will fail.
    scores: dict[tuple[int, int], tuple[float, float]] = field(default_factory=dict)
    # Box scores (espn-api.md §4). Set False to write none (a partial-tier Season).
    box_scores: bool = True
    # (week, team key) whose first starter's points are off by +1, so starters don't sum to the score
    bad_lineup: tuple[int, str] | None = None
    # (week, team key) whose 2nd starter has no actual stat row (didn't play) and whose bench Player is
    # one that exists only in this box score (not in players.json or the pool)
    quirks: tuple[int, str] | None = None
    # (week, team key) -> points added to that side's QB projection, to make a projected favourite.
    # By default every projection is points + 2, so the winner is always the projected favourite.
    projection_bonus: dict[tuple[int, str], float] = field(default_factory=dict)
    # (week, team key) -> points added to that side's first bench (BE) Player. Every bench Player scores
    # 4.5 by default, so a side's Bench points are 6 x 4.5 = 27.0; the IR Player's 4.5 never counts.
    bench_bonus: dict[tuple[int, str], float] = field(default_factory=dict)
    # (week, team key) whose 2nd bench Player has no actual stat row (didn't play), so their points are NULL
    bench_unplayed: tuple[int, str] | None = None
    # Manual score adjustments on a side's period-4 Matchup are set by `adjustments` (above)
    # Trades (espn-api.md §7), applied to the weekly rosters and lineups in effective-Week order
    trades: list[FixtureTrade] = field(default_factory=list)
    # Waiver claims, free-agent adds and drops (espn-api.md §7), applied with the trades in Week order
    moves: list[FixtureMove] = field(default_factory=list)
    # Points a Player scores every Week they're in a lineup. Starters' extra points come off the K
    # (slot 8) so each side still adds up to its score.
    lineup_points: dict[int, float] = field(default_factory=dict)
    # (week, from key, to key, slot): a Player moves between teams with no trade or add (unclean diff)
    stray_move: tuple[int, str, str, int] | None = None
    # Added to every team's transactionCounter.trades (to break the reconciliation)
    trade_counter_offset: int = 0

    TEAMS = 0
    REGULAR_PERIODS = 0
    PLAYOFF_TEAMS = 0
    PLAYOFF_PERIODS = 0
    WEEKS_PER_PLAYOFF_PERIOD = 1

    def __post_init__(self):
        assert len(self.teams_by_seed) == self.TEAMS
        self._ids = {t.key: i + 1 for i, t in enumerate(sorted(self.teams_by_seed, key=lambda t: t.key))}
        self._seed = {t.key: i + 1 for i, t in enumerate(self.teams_by_seed)}
        self._by_seed = {i + 1: t.key for i, t in enumerate(self.teams_by_seed)}
        self._schedule: list[dict] = []
        self._final_rank: dict[str, int] = {}
        self._regular_season()
        self._playoffs()
        self._set_scores()

    def _set_scores(self):
        for (period, index), (home, away) in self.scores.items():
            m = [m for m in self._schedule if m["matchupPeriodId"] == period][index]
            weeks = self._weeks(period)
            for side, pts in (("home", home), ("away", away)):
                m[side]["totalPoints"] = pts
                m[side]["pointsByScoringPeriod"] = {str(w): round(pts / len(weeks), 2) for w in weeks}
            m["winner"] = "HOME" if home > away else "AWAY" if away > home else "TIE"

    # -- simulation ----------------------------------------------------------

    def _regular_season(self):
        # A circle-method round robin; only the shape matters, records come from the seed
        order = [t.key for t in self.teams_by_seed]
        for period in range(1, self.REGULAR_PERIODS + 1):
            for i in range(self.TEAMS // 2):
                self._add(period, order[i], order[-1 - i], "NONE", home_wins=True)
            order = [order[0], order[-1], *order[1:-1]]
        # Record each manual adjustment on the team's period-4 Matchup, as ESPN does
        for key, amount in self.adjustments.items():
            m = next(m for m in self._schedule if m["matchupPeriodId"] == 4 and self._ids[key] in self._team_ids(m))
            side = m["home"] if m["home"]["teamId"] == self._ids[key] else m["away"]
            side["adjustment"] = amount
        if self.tie_period is not None:
            m = next(m for m in self._schedule if m["matchupPeriodId"] == self.tie_period)
            for side in (m["home"], m["away"]):
                side["totalPoints"] = 110.0
                side["pointsByScoringPeriod"] = {str(self.tie_period): 110.0}
            m["winner"] = "TIE"

    def _playoffs(self):
        raise NotImplementedError

    def _beats(self, a: str, b: str) -> bool:
        """Does a beat b in a playoff Matchup?"""
        if a in self.upsets and b not in self.upsets:
            return True
        if b in self.upsets and a not in self.upsets:
            return False
        return self._seed[a] < self._seed[b]

    def _weeks(self, period: int) -> list[int]:
        if period <= self.REGULAR_PERIODS:
            return [period]
        start = self.REGULAR_PERIODS + 1 + (period - self.REGULAR_PERIODS - 1) * self.WEEKS_PER_PLAYOFF_PERIOD
        return list(range(start, start + self.WEEKS_PER_PLAYOFF_PERIOD))

    def _add(self, period, home, away, tier, home_wins=None):
        if home_wins is None:
            home_wins = self._beats(home, away) if away else None
        hp, ap = (120.5, 101.25) if home_wins else (99.75, 118.0)
        entry = {
            "id": len(self._schedule) + 1,
            "matchupPeriodId": period,
            "playoffTierType": tier,
            "home": self._side(home, hp if away else BYE_POINTS, period),
            "winner": "UNDECIDED" if away is None else ("HOME" if home_wins else "AWAY"),
        }
        if away is not None:
            entry["away"] = self._side(away, ap, period)
        self._schedule.append(entry)
        if away is None:
            return home, None
        return (home, away) if home_wins else (away, home)

    def _side(self, key, points, period):
        weeks = self._weeks(period)
        return {
            "teamId": self._ids[key],
            "totalPoints": points,
            "adjustment": 0.0,
            "pointsByScoringPeriod": {str(w): round(points / len(weeks), 2) for w in weeks},
        }

    @staticmethod
    def _team_ids(m):
        return {m["home"]["teamId"], (m.get("away") or {}).get("teamId")}

    # -- ESPN-shaped documents ----------------------------------------------

    def settings(self) -> dict:
        total = self.REGULAR_PERIODS + self.PLAYOFF_PERIODS
        items = [{"statId": stat, "points": pts} for stat, pts in BASE_SCORING.items()]
        if self.te_premium:
            items.append(
                {"statId": 53, "points": 0.0, "pointsOverrides": {"1": 1.0, "2": 1.0, "3": 1.0, "4": 1.5, "16": 0.0}}
            )
        else:
            items.append({"statId": 53, "points": 1.0, "pointsOverrides": {"16": 0.0}})
        return {
            "id": int(LEAGUE_ID),
            "seasonId": self.year,
            "settings": {
                "name": self.league_name,
                "size": self.TEAMS,
                "scheduleSettings": {
                    "matchupPeriodCount": self.REGULAR_PERIODS,
                    "matchupPeriods": {str(p): self._weeks(p) for p in range(1, total + 1)},
                    "playoffTeamCount": self.PLAYOFF_TEAMS,
                    "playoffMatchupPeriodLength": self.WEEKS_PER_PLAYOFF_PERIOD,
                },
                "scoringSettings": {"scoringType": "H2H_POINTS", "scoringItems": items},
                "rosterSettings": {"lineupSlotCounts": dict(LINEUP_SLOTS)},
                "draftSettings": {"type": self.draft_type, "pickOrder": self.pick_order(), "keeperCount": 0},
            },
        }

    def teams(self) -> dict:
        teams = []
        for t in self.teams_by_seed:
            seed = self._seed[t.key]
            teams.append(
                {
                    "id": self._ids[t.key],
                    "name": t.name,
                    "abbrev": t.key[:4].upper(),
                    "owners": [t.member, *t.extra_members],
                    "primaryOwner": t.member,
                    "playoffSeed": seed,
                    "rankCalculatedFinal": self._final_rank[t.key],
                    "rankFinal": 0,
                    # Each executed trade counts once per side (espn-api.md §2)
                    "transactionCounter": {
                        "acquisitions": 0,
                        "drops": 0,
                        "trades": self.trade_counter_offset
                        + sum(1 for tr in self.trades if tr.executes and t.key in (tr.a, tr.b)),
                        "acquisitionBudgetSpent": 0,
                    },
                    "record": {
                        "overall": {
                            "wins": self.REGULAR_PERIODS - seed,
                            "losses": seed,
                            "ties": 0,
                            # ESPN's points for includes manual adjustments (espn-api.md §2)
                            "pointsFor": 1500.0 - seed + self.adjustments.get(t.key, 0.0),
                            "pointsAgainst": 1400.0 + seed,
                        }
                    },
                }
            )
        teams.sort(key=lambda t: t["id"])
        members = [
            {"id": t.member, "displayName": f"user{self._ids[t.key]}", "firstName": "X", "lastName": "Y"}
            for t in self.teams_by_seed
        ]
        return {"id": int(LEAGUE_ID), "seasonId": self.year, "teams": teams, "members": members}

    def matchups(self) -> dict:
        return {"id": int(LEAGUE_ID), "seasonId": self.year, "schedule": self._schedule}

    def pick_order(self) -> list[int]:
        """Round-1 order: worst seed first."""
        return [self._ids[t.key] for t in reversed(self.teams_by_seed)]

    def _picks(self) -> list[dict]:
        order = self.pick_order()
        picks = []
        for rnd in range(1, DRAFT_ROUNDS + 1):
            seq = order if rnd % 2 else list(reversed(order))  # snake (espn-api.md §6)
            for i, team_id in enumerate(seq):
                overall = (rnd - 1) * self.TEAMS + i + 1
                unrecorded = overall in self.unrecorded_picks
                picks.append(
                    {
                        "id": overall,
                        "overallPickNumber": overall,
                        "roundId": rnd,
                        "roundPickNumber": i + 1,
                        "teamId": team_id,
                        "playerId": -1 if unrecorded else fixture_player_id(overall),
                        "lineupSlotId": -1 if unrecorded else 20,
                        "autoDraftTypeId": 0,
                        "memberId": f"{{MEMBER-{team_id:04d}}}",  # personal in the real data: never exported
                        "bidAmount": 0,
                        "nominatingTeamId": 0,
                        "keeper": False,
                        "reservedForKeeper": False,
                        "tradeLocked": False,
                    }
                )
        return [p for p in picks if p["overallPickNumber"] not in self.missing_picks]

    def draft(self) -> dict:
        return {
            "id": int(LEAGUE_ID),
            "seasonId": self.year,
            "draftDetail": {"drafted": True, "inProgress": False, "picks": self._picks()},
        }

    def players(self) -> list[dict]:
        """players.json: every drafted Player plus one undrafted one (espn-api.md §5)."""
        ids = [p["playerId"] for p in self._picks() if p["playerId"] != -1] + [UNDRAFTED_PLAYER_ID]
        return [
            {
                "id": pid,
                "fullName": self.player_names.get(pid, fixture_player_name(pid)),
                "firstName": "X",
                "lastName": "Y",
                "defaultPositionId": fixture_player_position(pid),
                "proTeamId": fixture_player_pro_team(pid),
                "eligibleSlots": [],
                "droppable": True,
                "ownership": {"percentOwned": 50.0},
                "universeId": 0,
            }
            for pid in ids
            if pid not in self.unlisted_players
        ]

    def player_pool(self) -> dict:
        """player_pool.json (kona_player_info): every drafted Player plus undrafted ones, each with a
        season-total actual row (scoringPeriodId 0, statSourceId 0, statSplitTypeId 0) whose appliedTotal
        is the Player's Season points (espn-api.md §5; GLOSSARY: Season points)."""
        entries = []
        listed = {p["id"]: p for p in self.players()}
        extra = {UNDRAFTED_PLAYER_ID: (3, 50.0), **self.undrafted}
        drafted = [p["playerId"] for p in self._picks() if p["playerId"] != -1]
        rostered = [pid for pid in self.player_points if pid not in drafted and pid not in extra]
        for pid in drafted + list(extra) + rostered:
            if pid in rostered:  # a lineup Player or free agent given Season points
                name, position, pro_team = lineup_player(pid)
                points = self.player_points[pid]
            elif pid in extra:
                position, points = extra[pid]
                points = self.pool_points_by_position.get(position, points)
                name, pro_team = f"Undrafted Fixture {pid}", 0
            else:
                position, name, pro_team = (fixture_player_position(pid), fixture_player_name(pid),
                                            fixture_player_pro_team(pid))  # fmt: skip
                name = listed.get(pid, {}).get("fullName", self.player_names.get(pid, name))
                points = self.player_points.get(
                    pid, self.pool_points_by_position.get(position, fixture_player_points(pid))
                )
            stats = [
                # A projected row and a weekly row, which the loader must ignore
                {"seasonId": self.year, "scoringPeriodId": 0, "statSourceId": 1, "statSplitTypeId": 0,
                 "appliedTotal": 999.0},
                {"seasonId": self.year, "scoringPeriodId": 1, "statSourceId": 0, "statSplitTypeId": 1,
                 "appliedTotal": 12.5},
            ]  # fmt: skip
            if pid not in self.pool_without_points:
                stats.append(
                    {
                        "seasonId": self.year,
                        "scoringPeriodId": 0,
                        "statSourceId": 0,
                        "statSplitTypeId": 0,
                        "appliedTotal": points,
                    }  # fmt: skip
                )
            entries.append(
                {
                    "id": pid,
                    "onTeamId": 0,
                    "status": "FREEAGENT",
                    "player": {
                        "id": pid,
                        "fullName": name,
                        "defaultPositionId": position,
                        "proTeamId": pro_team,
                        "stats": stats,
                    },
                }
            )
        return {"players": entries, "positionAgainstOpponent": {}}

    def write(self, archive: Path) -> None:
        d = archive / str(self.year)
        d.mkdir(parents=True, exist_ok=True)
        (d / "players.json").write_text(json.dumps(self.players(), indent=1), encoding="utf-8")
        (d / "player_pool.json").write_text(json.dumps(self.player_pool(), indent=1), encoding="utf-8")
        for name, doc in (
            ("league_mSettings", self.settings()),
            ("league_mTeam", self.teams()),
            ("league_mMatchupScore", self.matchups()),
            ("league_mDraftDetail", self.draft()),
        ):
            (d / f"{name}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        if self.box_scores:
            last = self._weeks(self.REGULAR_PERIODS + self.PLAYOFF_PERIODS)[-1]
            for week in range(1, last + 1):
                for name, doc in (
                    ("boxscore", self.box_score(week)),
                    ("roster", self.roster_doc(week)),
                    ("transactions", self.transactions_doc(week)),
                ):
                    (d / f"{name}_w{week:02d}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")

    # -- rosters and trades (espn-api.md §4 weekly rosters, §7) -----------------

    def team_id(self, key: str) -> int:
        return self._ids[key]

    def drafted(self, key: str, rnd: int) -> int:
        """playerId of team `key`'s Pick in round `rnd`."""
        return next(p["playerId"] for p in self._picks() if p["teamId"] == self._ids[key] and p["roundId"] == rnd)

    def _replay(self) -> tuple[dict[int, dict[str, list[int]]], dict[int, list], dict[int, tuple]]:
        """Play the Season's trades and executed moves Week by Week (moves first within a Week).

        Returns each Week's rosters (team key -> Players by lineup slot), each executed trade's legs
        (playerId, from key, to key, slot) by id(trade), and each executed move's (added, dropped) by id(move).
        """
        roster = {k: [lineup_player_id(i, s) for s in range(len(LINEUP))] for k, i in self._ids.items()}
        events = sorted(
            [(m.week, 0, n, m) for n, m in enumerate(self.moves) if m.executes]
            + [(t.effective_week, 1, n, t) for n, t in enumerate(self.trades) if t.executes and t.moves]
        )
        snapshots, legs_of, items_of = {}, {}, {}
        for week in range(1, self._weeks(self.REGULAR_PERIODS + self.PLAYOFF_PERIODS)[-1] + 1):
            for _, kind, _, ev in (e for e in events if e[0] == week):
                if kind == 0:
                    held = roster[ev.team][ev.slot]
                    roster[ev.team][ev.slot] = (
                        ev.add if ev.add is not None else 86000 + self._ids[ev.team] * 100 + ev.slot
                    )
                    items_of[id(ev)] = (ev.add, held if ev.drop else None)
                    continue
                if ev.draft_round is not None:
                    legs = [(self.drafted(ev.a, ev.draft_round), ev.a, ev.b, ev.slots[0]),
                            (self.drafted(ev.b, ev.draft_round), ev.b, ev.a, ev.slots[0])]  # fmt: skip
                else:
                    legs = self._swap_legs(ev, roster)
                for pid, _, to, slot in legs:
                    roster[to][slot] = pid
                legs_of[id(ev)] = legs
            if self.stray_move and self.stray_move[0] == week:
                _, src, dst, slot = self.stray_move
                roster[dst][slot], roster[src][slot] = roster[src][slot], 80000 + self._ids[src] * 100 + slot
            snapshots[week] = {k: list(v) for k, v in roster.items()}
        return snapshots, legs_of, items_of

    def rosters(self, week: int) -> dict[str, list[int]]:
        """Each team's lineup Players, by slot index, in `week`, after every trade and move effective by then."""
        return self._replay()[0][week]

    def trade_legs(self) -> list[tuple[FixtureTrade, list[tuple[int, str, str, int]]]]:
        """Each executed trade that moves Players, with its legs (playerId, from key, to key, slot)."""
        legs_of = self._replay()[1]
        return [(t, legs_of[id(t)]) for t in self.trades if id(t) in legs_of]

    def _legs_of(self, trade: FixtureTrade) -> list[tuple[int, str, str, int]]:
        found = [legs for tr, legs in self.trade_legs() if tr is trade]
        if found:
            return found[0]
        # A vetoed or phantom trade: the legs it would have had
        if trade.draft_round is not None:
            return [(self.drafted(trade.a, trade.draft_round), trade.a, trade.b, trade.slots[0]),
                    (self.drafted(trade.b, trade.draft_round), trade.b, trade.a, trade.slots[0])]  # fmt: skip
        return self._swap_legs(trade, self.rosters(trade.week))

    @staticmethod
    def _swap_legs(trade: FixtureTrade, roster: dict[str, list[int]]) -> list[tuple[int, str, str, int]]:
        """a's slots[i] player moves into b's b_slots[i] (default: the same slot) and b's moves back."""
        a, b = roster[trade.a], roster[trade.b]
        return [
            leg
            for s, t in zip(trade.slots, trade.b_slots or trade.slots, strict=True)
            for leg in ((a[s], trade.a, trade.b, t), (b[t], trade.b, trade.a, s))
        ]

    def roster_doc(self, week: int) -> dict:
        """roster_wNN.json: teams[].roster.entries[] (espn-api.md §4), the lineup Players that Week."""
        teams = []
        for key, pids in sorted(self.rosters(week).items(), key=lambda kv: self._ids[kv[0]]):
            team_id = self._ids[key]
            entries = []
            for (slot, _), pid in zip(LINEUP, pids, strict=True):
                name, position, pro_team = lineup_player(pid)
                entries.append(
                    {"playerId": pid, "lineupSlotId": slot, "acquisitionType": None, "acquisitionDate": None,
                     "playerPoolEntry": {"id": pid, "onTeamId": team_id,
                                         "player": {"id": pid, "fullName": name, "defaultPositionId": position,
                                                    "proTeamId": pro_team}}}
                )  # fmt: skip
            teams.append({"id": team_id, "roster": {"entries": entries}})
        return {"id": int(LEAGUE_ID), "seasonId": self.year, "scoringPeriodId": week, "teams": teams}

    def transactions_doc(self, week: int) -> dict:
        """transactions_wNN.json (mTransactions2, espn-api.md §7): every row of the trades accepted this Week,
        plus a cancelled proposal and a declined one that the loader must ignore."""
        rows = [
            {"id": f"noise-proposal-{week}", "type": "TRADE_PROPOSAL", "status": "CANCELED", "teamId": 1,
             "scoringPeriodId": week, "proposedDate": 1_600_000_000_000 + week, "items": []},
            {"id": f"noise-decline-{week}", "type": "TRADE_DECLINE", "teamId": 2, "scoringPeriodId": week,
             "relatedTransactionId": f"noise-proposal-{week}", "proposedDate": 1_600_000_000_000 + week,
             "items": []},
        ]  # fmt: skip
        for n, tr in enumerate(self.trades):
            if tr.week == week:
                rows.extend(self._trade_rows(n, tr))
        items_of = self._replay()[2]
        for n, mv in enumerate(self.moves):
            if mv.week == week:
                rows.append(self._move_row(n, mv, items_of))
        return {"id": int(LEAGUE_ID), "seasonId": self.year, "scoringPeriodId": week, "transactions": rows}

    def _trade_rows(self, n: int, tr: FixtureTrade) -> list[dict]:
        a, b = self._ids[tr.a], self._ids[tr.b]
        tid = f"{self.year}-trade-{n:02d}"
        items = [{"type": "TRADE", "playerId": pid, "fromTeamId": self._ids[src], "toTeamId": self._ids[dst],
                  "fromLineupSlotId": -1, "toLineupSlotId": -1, "isKeeper": False}
                 for pid, src, dst, _ in self._legs_of(tr)]  # fmt: skip
        when = 1_600_000_000_000 + tr.week * 604_800_000 + n
        base = {"teamId": a, "scoringPeriodId": tr.week, "proposedDate": when, "isPending": False, "bidAmount": 0,
                "memberId": f"{{MEMBER-{a:04d}}}", "isLeagueManager": False}  # fmt: skip
        if tr.legs:  # 2018: legs on TRADE_ACCEPT; status PENDING + PROCESS; no relatedTransactionId
            accept = {**base, "id": f"{tid}-accept", "type": "TRADE_ACCEPT", "status": "PENDING",
                      "executionType": "PROCESS", "acceptedDate": when, "processDate": when + 172_800_000,
                      "items": items}  # fmt: skip
            if tr.team_actions:
                accept["teamActions"] = {str(a): "ACCEPTED", str(b): "INVOLVED"}
            return [
                {**base, "id": f"{tid}-proposal", "type": "TRADE_PROPOSAL", "status": "PENDING", "teamId": b,
                 "items": items},
                accept,
                {**base, "id": f"{tid}-uphold", "type": "TRADE_UPHOLD", "teamId": 3, "items": items},
            ]  # fmt: skip
        # 2019 on: rows share relatedTransactionId (the proposal, absent from the archive); no legs, no status
        related = {**base, "relatedTransactionId": f"{tid}-proposal"}
        accept = {**related, "id": f"{tid}-accept", "type": "TRADE_ACCEPT", "executionType": "EXECUTE", "items": []}
        if tr.team_actions:
            accept["teamActions"] = {str(a): "ACCEPTED", str(b): "INVOLVED"}
        rows = [accept, {**related, "id": f"{tid}-uphold", "type": "TRADE_UPHOLD", "teamId": 3, "items": []}]
        if tr.second_accept:
            rows.append({**related, "id": f"{tid}-accept-2", "type": "TRADE_ACCEPT", "status": "EXECUTED",
                         "executionType": "PROCESS", "processDate": when + 86_400_000, "items": items})  # fmt: skip
        if tr.veto:
            rows.append({**related, "id": f"{tid}-veto", "type": "TRADE_VETO", "teamId": 4, "items": [],
                         "isLeagueManager": tr.veto == "commissioner"})  # fmt: skip
        return rows

    def _move_row(self, n: int, mv: FixtureMove, items_of: dict[int, tuple]) -> dict:
        team = self._ids[mv.team]
        if id(mv) in items_of:
            added, dropped = items_of[id(mv)]
        else:  # didn't execute: the row still names the Players it would have moved
            held = self.rosters(mv.week)[mv.team][mv.slot] if mv.week > 0 else None
            added, dropped = mv.add, held if mv.drop else None
        items = []
        if added is not None:
            items.append({"type": "ADD", "playerId": added, "fromTeamId": 0, "toTeamId": team,
                          "fromLineupSlotId": -1, "toLineupSlotId": 20, "isKeeper": False})  # fmt: skip
        if dropped is not None:
            items.append({"type": "DROP", "playerId": dropped, "fromTeamId": team, "toTeamId": 0,
                          "fromLineupSlotId": 20, "toLineupSlotId": -1, "isKeeper": False})  # fmt: skip
        execution = mv.execution_type or ("PROCESS" if mv.type == "WAIVER" else "EXECUTE")
        when = 1_600_000_000_000 + mv.week * 604_800_000 + 1_000 + n
        row = {"id": f"{self.year}-move-{n:02d}", "type": mv.type, "status": mv.status, "executionType": execution,
               "isPending": mv.status == "PENDING", "teamId": self._ids[mv.row_team or mv.team],
               "memberId": f"{{MEMBER-{team:04d}}}", "isLeagueManager": False, "scoringPeriodId": mv.week,
               "proposedDate": when, "bidAmount": 0, "items": items}  # fmt: skip
        if execution == "PROCESS":
            row["processDate"] = when + 3_600_000
        return row

    # -- box scores ------------------------------------------------------------

    def _period_of(self, week: int) -> int:
        return next(p for p in range(1, self.REGULAR_PERIODS + self.PLAYOFF_PERIODS + 1) if week in self._weeks(p))

    def box_score(self, week: int) -> dict:
        """boxscore_wNN.json: that period's Matchups, each side with its lineup for this Week. Starters'
        points add up to the side's pointsByScoringPeriod for the Week (espn-api.md §4)."""
        period = self._period_of(week)
        keys = {v: k for k, v in self._ids.items()}
        schedule = []
        for m in self._schedule:
            if m["matchupPeriodId"] != period:
                continue
            m = json.loads(json.dumps(m))
            for side in ("home", "away"):
                if side in m:
                    team_key = keys[m[side]["teamId"]]
                    total = m[side]["pointsByScoringPeriod"][str(week)]
                    m[side]["rosterForCurrentScoringPeriod"] = {"entries": self._lineup(week, team_key, total)}
            schedule.append(m)
        return {"id": int(LEAGUE_ID), "seasonId": self.year, "scoringPeriodId": week, "schedule": schedule}

    def _lineup(self, week: int, team_key: str, total: float) -> list[dict]:
        team_id = self._ids[team_key]
        roster = self.rosters(week)[team_key]
        share = round(total / len(STARTERS), 2)
        points = [share] * (len(STARTERS) - 1) + [round(total - share * (len(STARTERS) - 1), 2)]
        if self.bad_lineup == (week, team_key):
            points[0] = round(points[0] + 1, 2)
        if self.quirks == (week, team_key):  # the 2nd starter didn't play: the last starter scores their share
            points[-1], points[1] = round(points[-1] + points[1], 2), 0.0
        points += [4.5] * len(BENCH)
        k = len(STARTERS) - 1
        for i, pid in enumerate(roster):
            if pid in self.lineup_points and i != k:
                if i < len(STARTERS):  # the K keeps the side's total
                    points[k] = round(points[k] + points[i] - self.lineup_points[pid], 2)
                points[i] = self.lineup_points[pid]
        entries = []
        for i, ((slot, _), pts) in enumerate(zip(LINEUP, points, strict=True)):
            pid = roster[i]
            played = not (self.quirks == (week, team_key) and i == 1)
            if self.bench_unplayed == (week, team_key) and i == len(STARTERS) + 1:
                played = False
            if i == len(STARTERS):
                pts = round(pts + self.bench_bonus.get((week, team_key), 0.0), 2)
            if self.quirks == (week, team_key) and i == len(STARTERS):
                pid = 99000 + team_id  # only in this box score
            name, position, pro_team = (
                lineup_player(pid) if pid != 99000 + team_id else (f"Lineup {team_id}-{i:02d}", LINEUP[i][1], 1 + i)
            )
            bonus = self.projection_bonus.get((week, team_key), 0.0) if i == 0 else 0.0
            stats = [{"seasonId": self.year, "scoringPeriodId": week, "statSourceId": 1, "statSplitTypeId": 1,
                      "appliedTotal": round(pts + 2.0 + bonus, 2), "proTeamId": pro_team}]  # fmt: skip
            if played:
                actual = {"seasonId": self.year, "scoringPeriodId": week, "statSourceId": 0, "statSplitTypeId": 1}
                stats.append(
                    {**actual, "appliedTotal": pts, "proTeamId": pro_team, "externalId": f"40{week:02d}{i:02d}"}
                )
            entries.append(
                {
                    "lineupSlotId": slot,
                    "playerId": pid,
                    "playerPoolEntry": {
                        "id": pid,
                        "onTeamId": team_id,
                        "appliedStatTotal": pts if played else 0.0,
                        "player": {
                            "id": pid,
                            "fullName": name,
                            "defaultPositionId": position,
                            "proTeamId": pro_team,
                            "stats": stats,
                        },
                    },
                }
            )
        return entries


@dataclass
class Season2020Style(FixtureSeason):
    """A 12-team Season: 14 regular-season periods, 6 playoff teams, byes for seeds 1-2,
    a Third-place game and a 5th-place game in the last period (espn-api.md §3)."""

    # Seed 12 (worst regular season) wins its last consolation game and finishes 11th, above seed 11
    last_place_climbs: bool = False

    TEAMS = 12
    REGULAR_PERIODS = 14
    PLAYOFF_TEAMS = 6
    PLAYOFF_PERIODS = 3

    def _playoffs(self):
        by_seed = self._by_seed
        # Period 15: byes for seeds 1-2, 3v6, 4v5; losers' ladder for 7-12
        self._add(15, by_seed[1], None, WB)
        self._add(15, by_seed[2], None, WB)
        w36, l36 = self._add(15, by_seed[3], by_seed[6], WB)
        w45, l45 = self._add(15, by_seed[4], by_seed[5], WB)
        for a, b in ((7, 12), (8, 11), (9, 10)):
            self._add(15, by_seed[a], by_seed[b], LCL)
        # Period 16: 1 v lowest remaining seed, 2 v the other
        low, high = sorted((w36, w45), key=self._seed.get, reverse=True)
        s1w, s1l = self._add(16, by_seed[1], low, WB)
        s2w, s2l = self._add(16, by_seed[2], high, WB)
        self._add(16, *sorted((l36, l45), key=self._seed.get), WCL)
        for a, b in ((7, 10), (8, 9), (11, 12)):
            self._add(16, by_seed[a], by_seed[b], LCL)
        # Period 17: 5th-place game (listed first, same tier as the Third-place game), final,
        # Third-place game, losers' ladder
        fifth, sixth = self._add(17, *sorted((l36, l45), key=self._seed.get), WCL)
        champ, runner = self._add(17, *sorted((s1w, s2w), key=self._seed.get), WB)
        third, fourth = self._add(17, *sorted((s1l, s2l), key=self._seed.get), WCL)
        self._add(17, by_seed[7], by_seed[8], LCL)
        self._add(17, by_seed[9], by_seed[10], LCL)
        self._add(17, by_seed[11], by_seed[12], LCL, home_wins=not self.last_place_climbs)

        placed = [champ, runner, third, fourth, fifth, sixth]
        self._final_rank = {k: i + 1 for i, k in enumerate(placed)}
        for seed in range(7, 13):
            self._final_rank[by_seed[seed]] = seed
        if self.last_place_climbs:
            self._final_rank[by_seed[11]], self._final_rank[by_seed[12]] = 12, 11


@dataclass
class Season2018Style(FixtureSeason):
    """A 10-team Season: 13 regular-season periods, 4 playoff teams, no byes, and two-week
    playoff periods (14 = Weeks 14-15, 15 = Weeks 16-17). The Third-place game is the only
    WINNERS_CONSOLATION_LADDER Matchup (espn-api.md §3, §9)."""

    TEAMS = 10
    REGULAR_PERIODS = 13
    PLAYOFF_TEAMS = 4
    PLAYOFF_PERIODS = 2
    WEEKS_PER_PLAYOFF_PERIOD = 2

    def _playoffs(self):
        by_seed = self._by_seed
        # Period 14 (Weeks 14-15): semifinals 1v4, 2v3; losers' ladder for 5-10
        s1w, s1l = self._add(14, by_seed[1], by_seed[4], WB)
        s2w, s2l = self._add(14, by_seed[2], by_seed[3], WB)
        for a, b in ((5, 10), (6, 9), (7, 8)):
            self._add(14, by_seed[a], by_seed[b], LCL)
        # Period 15 (Weeks 16-17): final, Third-place game, losers' ladder
        champ, runner = self._add(15, *sorted((s1w, s2w), key=self._seed.get), WB)
        third, fourth = self._add(15, *sorted((s1l, s2l), key=self._seed.get), WCL)
        for a, b in ((5, 6), (7, 8), (9, 10)):
            self._add(15, by_seed[a], by_seed[b], LCL)

        self._final_rank = {k: i + 1 for i, k in enumerate([champ, runner, third, fourth])}
        for seed in range(5, 11):
            self._final_rank[by_seed[seed]] = seed


def write_owners(path: Path, owners: dict[str, list[str]]) -> Path:
    """Write an owners.yaml mapping display name -> ESPN member IDs."""
    doc = {"owners": [{"name": name, "espn_members": members} for name, members in owners.items()]}
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


# Invented people: key -> (Owner display name, team name, member ID)
PEOPLE = {
    "quinn": ("Quinn Harrow", "Harrow Hammers", "{00000000-0000-4000-8000-000000000001}"),
    "pell": ("Pell Vantor", "Vantor Vipers", "{00000000-0000-4000-8000-000000000002}"),
    "odie": ("Odie Brask", "Brask Bruisers", "{00000000-0000-4000-8000-000000000003}"),
    "rue": ("Rue Calloway", "Calloway Comets", "{00000000-0000-4000-8000-000000000004}"),
    "tamsin": ("Tamsin Oake", "Oake Oracles", "{00000000-0000-4000-8000-000000000005}"),
    "lyle": ("Lyle Fenwick", "Fenwick Foxes", "{00000000-0000-4000-8000-000000000006}"),
    "marlo": ("Marlo Quist", "Quist Quakes", "{00000000-0000-4000-8000-000000000007}"),
    "ines": ("Ines Dorrow", "Dorrow Drakes", "{00000000-0000-4000-8000-000000000008}"),
    "abel": ("Abel Trice", "Trice Tritons", "{00000000-0000-4000-8000-000000000009}"),
    "wren": ("Wren Solano", "Solano Sparks", "{00000000-0000-4000-8000-000000000010}"),
    "cass": ("Cass Imber", "Imber Embers", "{00000000-0000-4000-8000-000000000011}"),
    "jory": ("Jory Paxton", "Paxton Pistons", "{00000000-0000-4000-8000-000000000012}"),
    # A 13th Owner, for Seasons where someone joins and someone else leaves
    "nell": ("Nell Ashgrove", "Ashgrove Aces", "{00000000-0000-4000-8000-000000000013}"),
}


def team(key: str, *, name: str | None = None, member: str | None = None) -> Team:
    _, default_name, default_member = PEOPLE[key]
    return Team(key, name or default_name, member or default_member)


def default_owners() -> dict[str, list[str]]:
    return {display: [member] for display, _, member in PEOPLE.values()}
