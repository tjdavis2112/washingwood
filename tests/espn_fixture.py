"""Synthetic, ESPN-shaped fixture archives for Seam 1 tests.

Shapes follow docs/research/espn-api.md (§1 settings, §2 teams, §3 matchups). Every Owner,
member ID and team name is invented (ADR-0007). Nothing here derives from the real archive.

Playoff rule, so expected results are easy to reason about: the higher seed wins every
playoff Matchup unless the other team is listed in `upsets`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

LEAGUE_ID = "999001"  # invented


@dataclass
class Team:
    """One Franchise in a fixture Season."""

    key: str  # test handle, e.g. "quinn"
    name: str  # team name that Season
    member: str  # invented ESPN member ID ("{...}" form)


@dataclass
class Season2020Style:
    """A 12-team Season: 14 regular-season periods, 6 playoff teams, byes for seeds 1-2,
    a Third-place game and a 5th-place game in the last period (espn-api.md §3)."""

    year: int
    teams_by_seed: list[Team]  # index 0 = seed 1
    upsets: set[str] = field(default_factory=set)
    league_name: str = "Example Fantasy League"

    REGULAR_PERIODS = 14
    TOTAL_PERIODS = 17

    def __post_init__(self):
        assert len(self.teams_by_seed) == 12
        self._ids = {t.key: i + 1 for i, t in enumerate(sorted(self.teams_by_seed, key=lambda t: t.key))}
        self._seed = {t.key: i + 1 for i, t in enumerate(self.teams_by_seed)}
        self._schedule: list[dict] = []
        self._final_rank: dict[str, int] = {}
        self._simulate()

    # -- simulation ----------------------------------------------------------

    def _beats(self, a: str, b: str) -> bool:
        """Does a beat b in a playoff Matchup?"""
        if a in self.upsets and b not in self.upsets:
            return True
        if b in self.upsets and a not in self.upsets:
            return False
        return self._seed[a] < self._seed[b]

    def _add(self, period, home, away, tier, home_wins=None):
        if home_wins is None:
            home_wins = self._beats(home, away) if away else None
        hp, ap = (120.5, 101.25) if home_wins else (99.75, 118.0)
        entry = {
            "id": len(self._schedule) + 1,
            "matchupPeriodId": period,
            "playoffTierType": tier,
            "home": self._side(home, hp if away else 0.0, period),
            "winner": "UNDECIDED" if away is None else ("HOME" if home_wins else "AWAY"),
        }
        if away is not None:
            entry["away"] = self._side(away, ap, period)
        self._schedule.append(entry)
        if away is None:
            return home, None
        return (home, away) if home_wins else (away, home)

    def _side(self, key, points, period):
        return {
            "teamId": self._ids[key],
            "totalPoints": points,
            "adjustment": 0.0,
            "pointsByScoringPeriod": {str(period): points},
        }

    def _simulate(self):
        keys = [t.key for t in self.teams_by_seed]
        by_seed = dict(enumerate(keys, start=1))
        # Regular season: a circle-method round robin; results don't matter to the tracer
        order = list(keys)
        for period in range(1, self.REGULAR_PERIODS + 1):
            for i in range(6):
                self._add(period, order[i], order[11 - i], "NONE", home_wins=True)
            order = [order[0], order[-1], *order[1:-1]]

        wb, wcl, lcl = "WINNERS_BRACKET", "WINNERS_CONSOLATION_LADDER", "LOSERS_CONSOLATION_LADDER"
        # Period 15: byes for seeds 1-2, 3v6, 4v5; losers' ladder for 7-12
        self._add(15, by_seed[1], None, wb)
        self._add(15, by_seed[2], None, wb)
        w36, l36 = self._add(15, by_seed[3], by_seed[6], wb)
        w45, l45 = self._add(15, by_seed[4], by_seed[5], wb)
        for a, b in ((7, 12), (8, 11), (9, 10)):
            self._add(15, by_seed[a], by_seed[b], lcl)
        # Period 16: 1 v lowest remaining seed, 2 v the other
        low, high = sorted((w36, w45), key=self._seed.get, reverse=True)
        s1w, s1l = self._add(16, by_seed[1], low, wb)
        s2w, s2l = self._add(16, by_seed[2], high, wb)
        self._add(16, *sorted((l36, l45), key=self._seed.get), wcl)
        for a, b in ((7, 10), (8, 9), (11, 12)):
            self._add(16, by_seed[a], by_seed[b], lcl)
        # Period 17: final, Third-place game, 5th-place game, losers' ladder
        champ, runner = self._add(17, *sorted((s1w, s2w), key=self._seed.get), wb)
        third, fourth = self._add(17, *sorted((s1l, s2l), key=self._seed.get), wcl)
        fifth, sixth = self._add(17, *sorted((l36, l45), key=self._seed.get), wcl)
        for a, b in ((7, 8), (9, 10), (11, 12)):
            self._add(17, by_seed[a], by_seed[b], lcl)

        placed = [champ, runner, third, fourth, fifth, sixth]
        self._final_rank = {k: i + 1 for i, k in enumerate(placed)}
        for seed in range(7, 13):
            self._final_rank[by_seed[seed]] = seed

    # -- ESPN-shaped documents ----------------------------------------------

    def settings(self) -> dict:
        periods = {str(p): [p] for p in range(1, self.TOTAL_PERIODS + 1)}
        return {
            "id": int(LEAGUE_ID),
            "seasonId": self.year,
            "settings": {
                "name": self.league_name,
                "size": 12,
                "scheduleSettings": {
                    "matchupPeriodCount": self.REGULAR_PERIODS,
                    "matchupPeriods": periods,
                    "playoffTeamCount": 6,
                    "playoffMatchupPeriodLength": 1,
                },
                "scoringSettings": {
                    "scoringType": "H2H_POINTS",
                    "scoringItems": [
                        {"statId": 4, "points": 4.0},
                        {"statId": 53, "points": 1.0, "pointsOverrides": {"16": 0.0}},
                    ],
                },
                "rosterSettings": {
                    "lineupSlotCounts": {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "16": 1, "17": 1, "20": 7, "21": 0}
                },
            },
        }

    def teams(self) -> dict:
        teams = []
        for t in self.teams_by_seed:
            seed = self._seed[t.key]
            wins = 14 - seed  # seed 1 has the best record
            teams.append(
                {
                    "id": self._ids[t.key],
                    "name": t.name,
                    "abbrev": t.key[:4].upper(),
                    "owners": [t.member],
                    "primaryOwner": t.member,
                    "playoffSeed": seed,
                    "rankCalculatedFinal": self._final_rank[t.key],
                    "rankFinal": 0,
                    "record": {
                        "overall": {
                            "wins": wins,
                            "losses": 14 - wins,
                            "ties": 0,
                            "pointsFor": 1500.0 - seed,
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

    def write(self, archive: Path) -> None:
        d = archive / str(self.year)
        d.mkdir(parents=True, exist_ok=True)
        for name, doc in (
            ("league_mSettings", self.settings()),
            ("league_mTeam", self.teams()),
            ("league_mMatchupScore", self.matchups()),
        ):
            (d / f"{name}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")


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
}


def team(key: str, *, name: str | None = None, member: str | None = None) -> Team:
    _, default_name, default_member = PEOPLE[key]
    return Team(key, name or default_name, member or default_member)


def default_owners() -> dict[str, list[str]]:
    return {display: [member] for display, _, member in PEOPLE.values()}
