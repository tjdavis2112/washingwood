"""Export site-data documents (contract/site-data.schema.json) from core.* and stats.*.

Output is deterministic: stable ordering, no timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import Connection

from washingwood.loader import THIRD_PLACE
from washingwood.owners import slugify


class ExportError(ValueError):
    """The loaded data can't be turned into a valid site-data document."""


def league_summary(conn: Connection) -> dict:
    seasons = conn.execute("SELECT year, team_count FROM core.seasons ORDER BY year").fetchall()
    if not seasons:
        raise ExportError("no Seasons loaded")
    latest = seasons[-1][0]
    champ = conn.execute("SELECT display_name, team_name FROM stats.champions WHERE year = %s", (latest,)).fetchall()
    if len(champ) != 1:
        raise ExportError(f"Season {latest}: expected one Champion, found {len(champ)}")
    name, team_name = champ[0]
    league_name = conn.execute(
        "SELECT l.name FROM core.leagues l JOIN core.seasons s USING (league_id) WHERE s.year = %s", (latest,)
    ).fetchone()[0]
    return {
        "leagueName": league_name,
        "seasons": [{"year": y, "teamCount": n} for y, n in seasons],
        "champion": {"owner": _owner_ref(name), "teamName": team_name, "year": latest},
    }


def trophy_shelf(conn: Connection) -> dict:
    """Every Owner, former Owners included, ordered by titles, then runner-ups (both descending), then name."""
    rows = conn.execute(
        """SELECT display_name, current_team_name, title_seasons, runner_up_seasons,
                  first_season, last_season, is_former
           FROM stats.trophy_shelf
           ORDER BY cardinality(title_seasons) DESC, cardinality(runner_up_seasons) DESC, display_name"""
    ).fetchall()
    return {
        "owners": [
            {
                "owner": _owner_ref(name),
                "currentTeamName": team,
                "titles": list(titles),
                "runnerUps": list(runner_ups),
                "firstSeason": first,
                "lastSeason": last,
                "isFormer": is_former,
            }
            for name, team, titles, runner_ups, first, last, is_former in rows
        ]
    }


def owner_index(conn: Connection) -> dict:
    """Every Owner for the Owners index, in trophy-shelf order. The regular-season record is the sum of
    the Owner's Season records in the standings (stats.owner_career), so playoffs and consolation
    Matchups are left out."""
    rows = conn.execute(
        """SELECT t.display_name, t.current_team_name, t.first_season, t.last_season, t.is_former,
                  t.title_seasons, t.runner_up_seasons, c.wins, c.losses, c.ties
           FROM stats.trophy_shelf t
           JOIN stats.owner_career c USING (owner_id)
           ORDER BY cardinality(t.title_seasons) DESC, cardinality(t.runner_up_seasons) DESC, t.display_name"""
    ).fetchall()
    return {
        "owners": [
            {
                "owner": _owner_ref(name),
                "currentTeamName": team,
                "firstSeason": first,
                "lastSeason": last,
                "isFormer": is_former,
                "titles": list(titles),
                "runnerUps": list(runner_ups),
                "regularSeason": _record(int(w), int(lost), int(tied)),
            }
            for name, team, first, last, is_former, titles, runner_ups, w, lost, tied in rows
        ]
    }


def owner_documents(conn: Connection) -> dict[str, dict]:
    """One Owner document per Owner, keyed by slug. Records, playoff record and head-to-head follow
    GLOSSARY.md (Playoff record, Playoff appearance) through stats.owner_games."""
    head = {
        owner_id: (name, team, first, last, is_former, list(titles), list(runner_ups))
        for owner_id, name, team, first, last, is_former, titles, runner_ups in conn.execute(
            """SELECT owner_id, display_name, current_team_name, first_season, last_season, is_former,
                      title_seasons, runner_up_seasons
               FROM stats.trophy_shelf"""
        ).fetchall()
    }
    seasons: dict[int, list[dict]] = {owner_id: [] for owner_id in head}
    appearances: dict[int, list[int]] = {owner_id: [] for owner_id in head}
    for owner_id, year, team, w, lost, tied, pf, pa, seed, rank, playoff_teams, is_last in conn.execute(
        """SELECT st.owner_id, st.year, st.team_name, st.wins, st.losses, st.ties, st.points_for,
                  st.points_against, st.playoff_seed, st.final_rank, s.playoff_team_count,
                  st.franchise_id = lp.franchise_id
           FROM stats.standings st
           JOIN core.seasons s       ON s.year = st.year
           JOIN stats.last_place lp ON lp.year = st.year
           ORDER BY st.year DESC"""
    ).fetchall():
        seasons[owner_id].append(
            {
                "year": year,
                "teamName": team,
                "record": _record(w, lost, tied),
                "pointsFor": float(pf),
                "pointsAgainst": float(pa),
                "playoffSeed": seed,
                "finalRank": rank,
                "podiumPlace": rank if rank <= 3 else None,
                "isLastPlace": is_last,
            }
        )
        if seed <= playoff_teams:  # Playoff appearance: a first-round bye counts
            appearances[owner_id].append(year)
    playoffs = {owner_id: _record(0, 0, 0) for owner_id in head}
    for owner_id, w, lost, tied in conn.execute(
        """SELECT owner_id, count(*) FILTER (WHERE result = 'W'), count(*) FILTER (WHERE result = 'L'),
                  count(*) FILTER (WHERE result = 'T')
           FROM stats.owner_games WHERE kind = 'playoff' GROUP BY owner_id"""
    ).fetchall():
        playoffs[owner_id] = _record(w, lost, tied)
    h2h: dict[int, list[dict]] = {owner_id: [] for owner_id in head}
    for owner_id, opp, rw, rl, rt, pw, pl, pt, meetings in conn.execute(
        """SELECT owner_id, opponent_owner_id, regular_wins, regular_losses, regular_ties,
                  playoff_wins, playoff_losses, playoff_ties, meetings
           FROM stats.head_to_head"""
    ).fetchall():
        h2h[owner_id].append(
            {
                "opponent": _owner_ref(head[opp][0]),
                "regularSeason": _record(rw, rl, rt),
                "playoffs": _record(pw, pl, pt),
                "meetings": meetings,
            }
        )

    drafts = _owner_drafts(conn, head)

    docs = {}
    for owner_id, (name, team, first, last, is_former, titles, runner_ups) in head.items():
        rows = seasons[owner_id]
        drafted = [d["year"] for d in drafts[owner_id]]
        if drafted != [r["year"] for r in rows]:
            raise ExportError(
                f"Owner {name}: Draft Picks for Seasons {drafted}, but played {[r['year'] for r in rows]}"
            )
        regular = {k: sum(r["record"][k] for r in rows) for k in ("wins", "losses", "ties")}
        games = sum(regular.values())
        if not games:
            raise ExportError(f"Owner {name} has no regular-season games")
        ref = _owner_ref(name)
        docs[ref["slug"]] = {
            "owner": ref,
            "currentTeamName": team,
            "firstSeason": first,
            "lastSeason": last,
            "isFormer": is_former,
            "trophies": {
                "titles": titles,
                "runnerUps": runner_ups,
                "thirds": sorted(r["year"] for r in rows if r["podiumPlace"] == 3),
            },
            "career": {
                "regularSeason": regular,
                "playoffs": playoffs[owner_id],
                "avgPointsFor": round(sum(r["pointsFor"] for r in rows) / games, 2),
                "avgPointsAgainst": round(sum(r["pointsAgainst"] for r in rows) / games, 2),
                "playoffAppearances": sorted(appearances[owner_id]),
                "lastPlaces": sorted(r["year"] for r in rows if r["isLastPlace"]),
            },
            "seasons": rows,
            "headToHead": sorted(h2h[owner_id], key=lambda h: (-h["meetings"], h["opponent"]["name"])),
            "draft": drafts[owner_id],
        }
    return dict(sorted(docs.items()))


def _owner_drafts(conn: Connection, owners) -> dict[int, list[dict]]:
    """owner_id -> one entry per Season, newest first: the Owner's Draft grade that Season and their
    Picks in pick order with Season points, Positional finish, Value over slot and Points over expected."""
    grades = {
        (owner_id, year): {"rank": rank, "of": team_count, "total": total}
        for owner_id, year, rank, team_count, total in conn.execute(
            """SELECT fo.owner_id, s.year, g.grade_rank, s.team_count, g.total_points_over_expected
               FROM stats.draft_grades g
               JOIN core.seasons s           ON s.season_id = g.season_id
               JOIN stats.franchise_owner fo ON fo.franchise_id = g.franchise_id"""
        ).fetchall()
    }
    drafts: dict[int, dict[int, dict]] = {owner_id: {} for owner_id in owners}
    for (
        owner_id,
        year,
        team,
        slot,
        overall,
        rnd,
        round_pick,
        name,
        position,
        nfl_team,
        points,
        finish,
        vos,
        poe,
    ) in conn.execute(
        """SELECT owner_id, year, team_name, draft_slot, overall_pick, round, round_pick, player_name, position,
                      nfl_team, points, positional_finish, value_over_slot, points_over_expected
               FROM stats.draft_board ORDER BY year DESC, overall_pick"""
    ).fetchall():
        entry = drafts[owner_id].setdefault(
            year, {"year": year, "teamName": team, "slot": slot, "grade": grades[(owner_id, year)], "picks": []}
        )
        entry["picks"].append(
            {
                "overall": overall,
                "round": rnd,
                "roundPick": round_pick,
                "player": None if name is None else {"name": name, "position": position, "nflTeam": nfl_team},
                "points": None if points is None else float(points),
                "positionalFinish": finish,
                "valueOverSlot": vos,
                "pointsOverExpected": poe,
            }
        )
    return {owner_id: list(by_year.values()) for owner_id, by_year in drafts.items()}


def season_document(conn: Connection, year: int) -> dict:
    """One Season's document. The bracket and weekly results join in #9 and #10."""
    team_count, data_tier = conn.execute(
        "SELECT team_count, data_tier FROM core.seasons WHERE year = %s", (year,)
    ).fetchone()
    standings = _standings(conn, year, team_count)
    podium = conn.execute(
        "SELECT final_rank, owner, team_name, wins, losses, ties FROM stats.podium WHERE year = %s ORDER BY final_rank",
        (year,),
    ).fetchall()
    places = [row[0] for row in podium]
    if places != [1, 2, 3]:
        raise ExportError(f"Season {year}: expected Podium places 1, 2, 3, found {places}")
    last = conn.execute(
        "SELECT owner, team_name, wins, losses, ties, playoff_seed FROM stats.last_place WHERE year = %s", (year,)
    ).fetchone()
    # Last place is the worst regular-season seed, which must equal the team count; anything else is bad data
    if last is None or last[5] != team_count:
        seed = None if last is None else last[5]
        raise ExportError(f"Season {year}: Last place should be seed {team_count}, found seed {seed}")
    last_owner, last_team, last_w, last_l, last_t, _ = last
    return {
        "year": year,
        "teamCount": team_count,
        "dataTier": data_tier,
        "podium": [
            {"place": place, "owner": _owner_ref(owner), "teamName": team, "record": _record(w, lost, tied)}
            for place, owner, team, w, lost, tied in podium
        ],
        "lastPlace": {
            "owner": _owner_ref(last_owner),
            "teamName": last_team,
            "record": _record(last_w, last_l, last_t),
            "punishment": None,  # Punishment content arrives after v1
        },
        "scoringFormat": _scoring_format(conn, year),
        "standings": standings,
        "bracket": _bracket(conn, year),
        "weeklyResults": _weekly_results(conn, year),
        "draft": _draft(conn, year),
    }


def _draft(conn: Connection, year: int) -> dict:
    """The Season's Draft: round-1 order by Draft slot, every Pick in order with its Season points,
    Positional finish, Value over slot and Points over expected, each drafted position's Replacement level,
    and the Draft grades (stats.draft_board, stats.replacement_level, stats.draft_grades)."""
    draft_type = conn.execute("SELECT draft_type FROM core.seasons WHERE year = %s", (year,)).fetchone()[0]
    rows = conn.execute(
        """SELECT overall_pick, round, round_pick, franchise_id, owner, team_name, draft_slot, player_name,
                  position, nfl_team, points, positional_finish, value_over_slot, points_over_expected
           FROM stats.draft_board WHERE year = %s ORDER BY overall_pick""",
        (year,),
    ).fetchall()
    if not rows:
        raise ExportError(f"Season {year}: no Draft picks loaded")
    order = sorted({(slot, owner, team) for _, rnd, _, _, owner, team, slot, *_ in rows if rnd == 1})
    picks, by_franchise = [], {}
    for overall, rnd, round_pick, fid, owner, _, _, name, position, nfl_team, points, finish, vos, poe in rows:
        pick = {
            "overall": overall,
            "round": rnd,
            "roundPick": round_pick,
            "owner": _owner_ref(owner),
            "player": None if name is None else {"name": name, "position": position, "nflTeam": nfl_team},
            "points": None if points is None else float(points),
            "positionalFinish": finish,
            "valueOverSlot": vos,
            "pointsOverExpected": poe,
        }
        picks.append(pick)
        by_franchise.setdefault(fid, []).append(pick)
    return {
        "type": draft_type,
        "rounds": max(p["round"] for p in picks),
        "order": [{"slot": slot, "owner": _owner_ref(owner), "teamName": team} for slot, owner, team in order],
        "picks": picks,
        "note": _draft_note(draft_type, sum(p["player"] is None for p in picks)),
        "replacement": _replacement(conn, year),
        "grades": _draft_grades(conn, year, by_franchise),
    }


def _draft_grades(conn: Connection, year: int, by_franchise: dict[int, list[dict]]) -> list[dict]:
    """One Draft grade per Franchise, by rank then Owner name, naming its best and worst Pick
    (highest / lowest Points over expected; the earliest Pick on a tie)."""
    grades = []
    for fid, rank, total, owner, team in conn.execute(
        """SELECT g.franchise_id, g.grade_rank, g.total_points_over_expected, fo.display_name, f.team_name
           FROM stats.draft_grades g
           JOIN core.seasons s           ON s.season_id = g.season_id
           JOIN core.franchises f        ON f.franchise_id = g.franchise_id
           JOIN stats.franchise_owner fo ON fo.franchise_id = g.franchise_id
           WHERE s.year = %s""",
        (year,),
    ).fetchall():
        graded = [p for p in by_franchise[fid] if p["pointsOverExpected"] is not None]
        if not graded:
            raise ExportError(f"Season {year}: {owner} has no Pick with a recorded Player to grade")

        def named(p):
            return {k: p[k] for k in ("overall", "round", "roundPick", "player", "pointsOverExpected")}

        best = max(graded, key=lambda p: (p["pointsOverExpected"], -p["overall"]))
        worst = min(graded, key=lambda p: (p["pointsOverExpected"], p["overall"]))
        grades.append(
            {
                "rank": rank,
                "owner": _owner_ref(owner),
                "teamName": team,
                "total": total,
                "best": named(best),
                "worst": named(worst),
            }
        )
    return sorted(grades, key=lambda g: (g["rank"], g["owner"]["name"]))


def _replacement(conn: Connection, year: int) -> list[dict]:
    """Replacement level for every position drafted that Season, by position name."""
    rows = conn.execute(
        """SELECT rl.position, rl.replacement_finish, rl.replacement_points
           FROM stats.replacement_level rl JOIN core.seasons s ON s.season_id = rl.season_id
           WHERE s.year = %s AND rl.position IN (SELECT position FROM stats.draft_board WHERE year = %s)
           ORDER BY rl.position""",
        (year, year),
    ).fetchall()
    return [{"position": pos, "finish": finish, "points": float(points)} for pos, finish, points in rows]


# Starting slots in lineup order (espn-api.md §5); bench (BE) before IR
SLOT_ORDER = ["QB", "TQB", "RB", "RB/WR", "WR", "WR/TE", "TE", "OP", "FLEX", "D/ST", "K"]
BENCH_ORDER = ["BE", "IR"]


def box_score_documents(conn: Connection) -> dict[int, dict]:
    """box-scores/<year>.json for every Season with lineups: every played Matchup (byes have no Box
    score) with each side's lineups Week by Week, totals, Projected score and any manual adjustment."""
    docs = {}
    for season_id, year, roster in conn.execute(
        """SELECT season_id, year, roster_slots FROM core.seasons s
           WHERE EXISTS (SELECT 1 FROM core.lineup_entries le WHERE le.season_id = s.season_id) ORDER BY year"""
    ).fetchall():
        template = {slot: n for slot, n in (roster or {}).items() if slot not in BENCH_ORDER}
        lineups: dict[tuple[int, int], list] = {}
        for week, fid, slot, starter, name, position, nfl_team, pts, proj in conn.execute(
            """SELECT week, franchise_id, slot, is_starter, player_name, position, nfl_team, points, projected_points
               FROM stats.box_score_entries WHERE year = %s""",
            (year,),
        ).fetchall():
            lineups.setdefault((fid, week), []).append(
                {"slot": slot, "name": name, "position": position, "nflTeam": nfl_team,
                 "points": None if pts is None else float(pts), "projected": None if proj is None else float(proj),
                 "_starter": starter}
            )  # fmt: skip
        info = {
            fid: (owner, team)
            for fid, owner, team in conn.execute(
                "SELECT franchise_id, owner, team_name FROM stats.standings WHERE year = %s", (year,)
            ).fetchall()
        }
        matchups = []
        for period, first, last, home, away, hp, ap, hadj, aadj, winner, is_playoff, bracket, rnd in conn.execute(
            """SELECT matchup_period, first_week, last_week, home_franchise_id, away_franchise_id, home_points,
                      away_points, home_adjustment, away_adjustment, winner_franchise_id, is_playoff, bracket,
                      playoff_round
               FROM core.matchups WHERE season_id = %s AND away_franchise_id IS NOT NULL
               ORDER BY matchup_period, matchup_id""",
            (season_id,),
        ).fetchall():
            weeks = list(range(first, last + 1))
            kind = (
                "regular" if not is_playoff else "playoff" if bracket == "winners"
                else "thirdPlace" if rnd == THIRD_PLACE else "consolation"
            )  # fmt: skip

            matchups.append(
                {
                    "matchupPeriod": period,
                    "weeks": weeks,
                    "kind": kind,
                    "home": _box_score_side(
                        info[home], hp, hadj, [lineups.get((home, w), []) for w in weeks], weeks, template
                    ),
                    "away": _box_score_side(
                        info[away], ap, aadj, [lineups.get((away, w), []) for w in weeks], weeks, template
                    ),
                    "winner": None if winner is None else ("home" if winner == home else "away"),
                    "isTie": winner is None,
                }
            )
        docs[year] = {"year": year, "matchups": matchups}
    return docs


def _box_score_side(who: tuple[str, str], pts, adj, week_entries: list[list[dict]], weeks: list[int], template) -> dict:
    """One side of a Box score: starters in slot order, then bench and IR, for each Week; empty starting
    slots against the Season's roster template; the Projected score over the Week(s)."""
    owner, team = who
    week_docs, projected = [], 0.0
    for w, entries in zip(weeks, week_entries, strict=True):
        starters = sorted(
            (e for e in entries if e["_starter"]),
            key=lambda e: (SLOT_ORDER.index(e["slot"]) if e["slot"] in SLOT_ORDER else 99, e["name"]),
        )
        bench = sorted(
            (e for e in entries if not e["_starter"]), key=lambda e: (BENCH_ORDER.index(e["slot"]), e["name"])
        )
        filled = {slot: sum(e["slot"] == slot for e in starters) for slot in template}
        empty = [slot for slot in SLOT_ORDER if slot in template for _ in range(template[slot] - filled[slot])]
        projected += sum(e["projected"] or 0 for e in starters)
        week_docs.append(
            {
                "week": w,
                "starters": [_entry(e) for e in starters],
                "bench": [_entry(e) for e in bench],
                "emptySlots": empty,
            }
        )
    return {
        "owner": _owner_ref(owner),
        "teamName": team,
        "score": float(pts),
        "projected": round(projected, 2),
        "adjustment": float(adj or 0),
        "weeks": week_docs,
    }


def _entry(e: dict) -> dict:
    return {k: v for k, v in e.items() if not k.startswith("_")}


def matchups_document(conn: Connection) -> dict:
    """The Matchups section. Championship cards come from each Season's bracket final, so they always
    agree with the Season pages."""
    years = [y for (y,) in conn.execute("SELECT year FROM core.seasons ORDER BY year DESC").fetchall()]
    if not years:
        raise ExportError("no Seasons loaded")
    return {
        "championships": [_championship(conn, year) for year in years],
        "leaderboards": _leaderboards(conn),
        "rivalryGrid": _rivalry_grid(conn),
    }


def record_book_document(conn: Connection) -> dict:
    """The Record Book section. Last place comes from stats.last_place, the same source as the Season
    pages, so the two always agree."""
    rows = conn.execute(
        """SELECT lp.year, lp.owner, lp.team_name, lp.wins, lp.losses, lp.ties, st.points_for, s.scoring_label
           FROM stats.last_place lp
           JOIN stats.standings st ON st.franchise_id = lp.franchise_id
           JOIN core.seasons s ON s.year = lp.year
           ORDER BY lp.year DESC"""
    ).fetchall()
    if not rows:
        raise ExportError("no Seasons loaded")
    seasons = [
        {
            "year": year,
            "owner": _owner_ref(owner),
            "teamName": team,
            "record": _record(w, lost, tied),
            "pointsFor": float(pf),
            "scoringFormat": label,
        }
        for year, owner, team, w, lost, tied, pf, label in rows
    ]
    tally: dict[str, dict] = {}
    for row in seasons:
        entry = tally.setdefault(row["owner"]["slug"], {"owner": row["owner"], "count": 0, "years": []})
        entry["count"] += 1
        entry["years"].append(row["year"])
    for entry in tally.values():
        entry["years"].sort()
    return {
        "season": _season_records(conn),
        "allTime": _all_time_records(conn),
        "lastPlace": {
            "seasons": seasons,
            "tally": sorted(tally.values(), key=lambda e: (-e["count"], e["owner"]["name"])),
        },
    }


# Season record lists: (contract key, row field to rank by, True = highest first). Points rank per game
# (GLOSSARY: Points per game); ties go to the earlier Season, then Owner name.
SEASON_RECORDS = [
    ("bestWinPct", "winPct", True),
    ("worstWinPct", "winPct", False),
    ("mostPointsFor", "pointsPerGame", True),
    ("fewestPointsFor", "pointsPerGame", False),
    ("mostPointsAgainst", "pointsAgainstPerGame", True),
]


def _season_records(conn: Connection) -> dict:
    """Top-10 Franchise-Seasons for each Season record, from stats.season_records."""
    rows = [
        {
            "year": year,
            "owner": _owner_ref(owner),
            "teamName": team,
            "record": _record(w, lost, tied),
            "games": games,
            "winPct": float(pct),
            "pointsFor": float(pf),
            "pointsPerGame": float(ppg),
            "pointsAgainst": float(pa),
            "pointsAgainstPerGame": float(papg),
            "scoringFormat": label,
        }
        for year, owner, team, w, lost, tied, games, pct, pf, ppg, pa, papg, label in conn.execute(
            """SELECT year, owner, team_name, wins, losses, ties, games, win_pct, points_for, points_per_game,
                      points_against, points_against_per_game, scoring_label
               FROM stats.season_records"""
        ).fetchall()
    ]
    return {
        key: sorted(rows, key=lambda r: (-r[field] if high else r[field], r["year"], r["owner"]["name"]))[:10]
        for key, field, high in SEASON_RECORDS
    }


def _all_time_records(conn: Connection) -> list[dict]:
    """One row per Owner, former Owners included, ordered by wins (descending), then name."""
    rows = [
        {
            "owner": _owner_ref(owner),
            "seasons": seasons,
            "record": _record(w, lost, tied),
            "games": games,
            "winPct": float(pct),
            "pointsFor": float(pf),
            "pointsPerGame": float(ppg),
            "lastPlaces": last_places,
        }
        for owner, seasons, w, lost, tied, games, pct, pf, ppg, last_places in conn.execute(
            """SELECT owner, seasons, wins, losses, ties, games, win_pct, points_for, points_per_game, last_places
               FROM stats.owner_records"""
        ).fetchall()
    ]
    return sorted(rows, key=lambda r: (-r["record"]["wins"], r["owner"]["name"]))


def rivalry_documents(conn: Connection) -> dict[str, dict]:
    """One Rivalry document per pair of Owners who have played, keyed "<a>-vs-<b>" (slugs in alphabetical
    order). Records follow the Owner page's head-to-head rules; every game is listed, newest first."""
    pairs: dict[tuple[str, str], dict] = {}
    for row in conn.execute(
        """SELECT year, matchup_period, first_week, last_week, kind, in_record, home_owner, home_team, home_points,
                  away_owner, away_team, away_points, winner
           FROM stats.owner_pair_games ORDER BY year DESC, matchup_period DESC"""
    ).fetchall():
        year, period, first, last, kind, in_record, h_owner, h_team, hp, a_owner, a_team, ap, winner = row
        home, away = _owner_ref(h_owner), _owner_ref(a_owner)
        ordered = sorted([("home", home, h_team, hp), ("away", away, a_team, ap)], key=lambda x: x[1]["slug"])
        key = (ordered[0][1]["slug"], ordered[1][1]["slug"])
        doc = pairs.setdefault(key, {"owners": [ordered[0][1], ordered[1][1]], "games": []})
        scores = [float(x[3]) for x in ordered]
        winner_index = None if winner is None else next(i for i, x in enumerate(ordered) if x[0] == winner)
        doc["games"].append(
            {
                "year": year,
                "matchupPeriod": period,
                "weeks": list(range(first, last + 1)),
                "kind": kind,
                "inRecord": in_record,
                "teams": [{"teamName": x[2], "score": float(x[3])} for x in ordered],
                "winner": winner_index,
                "isTie": winner is None,
                "margin": round(abs(scores[0] - scores[1]), 2),
            }
        )
    docs = {}
    for (a, b), doc in sorted(pairs.items()):
        games, sides = doc["games"], []
        for i, ref in enumerate(doc["owners"]):
            regular, playoffs = _record(0, 0, 0), _record(0, 0, 0)
            for g in games:
                if not g["inRecord"]:
                    continue
                rec = regular if g["kind"] == "regular" else playoffs
                rec["ties" if g["isTie"] else "wins" if g["winner"] == i else "losses"] += 1
            wins = [g for g in games if g["inRecord"] and g["winner"] == i]
            # Largest Margin; the earliest game on a tie
            best = min(wins, key=lambda g: (-g["margin"], g["year"], g["matchupPeriod"])) if wins else None
            sides.append({"owner": ref, "regularSeason": regular, "playoffs": playoffs, "biggestWin": best})
        docs[f"{a}-vs-{b}"] = {"sides": sides, "meetings": sum(g["inRecord"] for g in games), "games": games}
    return docs


def _rivalry_grid(conn: Connection) -> dict:
    """Owners in Owner-index order, and each Owner's combined record (regular season plus playoffs,
    head-to-head rules) against every Owner they've played, in both directions."""
    owners = [e["owner"] for e in owner_index(conn)["owners"]]
    order = {o["slug"]: i for i, o in enumerate(owners)}
    records = []
    for owner, opponent, rw, rl, rt, pw, pl, pt in conn.execute(
        """SELECT a.display_name, b.display_name, h.regular_wins, h.regular_losses, h.regular_ties,
                  h.playoff_wins, h.playoff_losses, h.playoff_ties
           FROM stats.head_to_head h
           JOIN core.owners a ON a.owner_id = h.owner_id
           JOIN core.owners b ON b.owner_id = h.opponent_owner_id"""
    ).fetchall():
        records.append(
            {"owner": _owner_ref(owner)["slug"], "opponent": _owner_ref(opponent)["slug"],
             "wins": rw + pw, "losses": rl + pl, "ties": rt + pt}
        )  # fmt: skip
    records.sort(key=lambda r: (order[r["owner"]], order[r["opponent"]]))
    return {"owners": owners, "records": records}


LEADERBOARD_SIZE = 10


def _leaderboards(conn: Connection) -> dict:
    """Top-10 lists over the Counted Matchups (stats.counted_matchups). Ties go by Season, Week, then
    Owner name. Every row carries its Season's Scoring format, since scores across formats aren't
    comparable (GAMEPLAN)."""
    # franchise_id -> (Owner, team name, playoff seed), through franchise_owners (stats.standings)
    info = {
        fid: (owner, team, seed)
        for fid, owner, team, seed in conn.execute(
            "SELECT franchise_id, owner, team_name, playoff_seed FROM stats.standings"
        ).fetchall()
    }
    projections = {
        mid: (hp, ap)
        for mid, hp, ap in conn.execute(
            "SELECT matchup_id, home_projected, away_projected FROM stats.counted_projections"
        ).fetchall()
    }
    games, sides, projection_upsets = [], [], []
    for mid, year, label, period, week, is_playoff, home, away, hp, ap, winner in conn.execute(
        """SELECT matchup_id, year, scoring_label, matchup_period, week, is_playoff, home_franchise_id,
                  away_franchise_id, home_points, away_points, winner_franchise_id
           FROM stats.counted_matchups"""
    ).fetchall():
        kind = "playoff" if is_playoff else "regular"

        def side(fid, pts, is_playoff=is_playoff):
            owner, team, seed = info[fid]
            return {
                "owner": _owner_ref(owner),
                "teamName": team,
                "score": float(pts),
                "seed": seed if is_playoff else None,
            }

        home_side, away_side = side(home, hp), side(away, ap)
        is_tie = winner is None
        win, lose = (away_side, home_side) if winner == away else (home_side, away_side)
        base = {"year": year, "matchupPeriod": period, "weeks": [week], "kind": kind}
        games.append(
            {**base, "winner": win, "loser": lose, "isTie": is_tie,
             "margin": round(win["score"] - lose["score"], 2), "scoringFormat": label}
        )  # fmt: skip
        for team, opp in ((home_side, away_side), (away_side, home_side)):
            result = "tie" if is_tie else ("win" if team is win else "loss")
            sides.append({**base, "team": team, "opponent": opp, "result": result, "scoringFormat": label})
        # Projection upset (GLOSSARY): the side with the lower Projected score won
        if not is_tie and mid in projections and None not in projections[mid]:
            home_proj, away_proj = (float(x) for x in projections[mid])
            win_proj, lose_proj = (away_proj, home_proj) if winner == away else (home_proj, away_proj)
            if win_proj < lose_proj:
                projection_upsets.append(
                    {**games[-1], "winnerProjected": round(win_proj, 2), "loserProjected": round(lose_proj, 2),
                     "projectedDeficit": round(lose_proj - win_proj, 2)}
                )  # fmt: skip

    def when(r, who):
        return (r["year"], r["matchupPeriod"], r[who]["owner"]["name"])

    upsets = [
        {**g, "seedGap": g["winner"]["seed"] - g["loser"]["seed"]}
        for g in games
        if g["kind"] == "playoff" and not g["isTie"] and g["winner"]["seed"] > g["loser"]["seed"]
    ]
    n = LEADERBOARD_SIZE
    return {
        "blowouts": sorted(games, key=lambda g: (-g["margin"], *when(g, "winner")))[:n],
        "closestGames": sorted(games, key=lambda g: (g["margin"], *when(g, "winner")))[:n],
        "highestScores": sorted(sides, key=lambda r: (-r["team"]["score"], *when(r, "team")))[:n],
        "lowestScores": sorted(sides, key=lambda r: (r["team"]["score"], *when(r, "team")))[:n],
        "playoffUpsets": sorted(upsets, key=lambda g: (-g["seedGap"], -g["margin"], *when(g, "winner")))[:n],
        "projectionUpsets": sorted(projection_upsets, key=lambda g: (-g["projectedDeficit"], *when(g, "winner")))[:n],
    }


def _championship(conn: Connection, year: int) -> dict:
    final_round = _bracket(conn, year)["rounds"][-1]
    (final,) = final_round["matchups"]
    if final["winner"] not in ("home", "away"):
        raise ExportError(f"Season {year}: the championship has no winner")
    champion, runner_up = (
        (final["home"], final["away"]) if final["winner"] == "home" else (final["away"], final["home"])
    )
    return {
        "year": year,
        "matchupPeriod": final_round["matchupPeriod"],
        "weeks": final_round["weeks"],
        "champion": champion,
        "runnerUp": runner_up,
        "margin": round(champion["score"] - runner_up["score"], 2),
    }


def draft_history(conn: Connection) -> dict:
    """The Draft section: every Season's first round, newest first (stats.draft_board)."""
    seasons: dict[int, dict] = {}
    for year, team_count, draft_type, overall, owner, team, name, position, nfl_team in conn.execute(
        """SELECT b.year, s.team_count, s.draft_type, b.overall_pick, b.owner, b.team_name, b.player_name,
                  b.position, b.nfl_team
           FROM stats.draft_board b JOIN core.seasons s USING (year)
           WHERE b.round = 1 ORDER BY b.year DESC, b.overall_pick"""
    ).fetchall():
        entry = seasons.setdefault(year, {"year": year, "teamCount": team_count, "type": draft_type, "firstRound": []})
        entry["firstRound"].append(
            {
                "overall": overall,
                "owner": _owner_ref(owner),
                "teamName": team,
                "player": None if name is None else {"name": name, "position": position, "nflTeam": nfl_team},
            }
        )
    for entry in seasons.values():
        if len(entry["firstRound"]) != entry["teamCount"]:
            raise ExportError(
                f"Season {entry['year']}: round 1 has {len(entry['firstRound'])} Picks for {entry['teamCount']} teams"
            )
    if not seasons:
        raise ExportError("no Draft picks loaded")
    return {"seasons": list(seasons.values()), **_all_time_picks(conn), "bestDrafters": _best_drafters(conn)}


ALL_TIME_PICKS = 10


def _all_time_picks(conn: Connection) -> dict:
    """The all-time Steals (highest Value over slot), Hits (highest Points over expected) and Busts
    (lowest Points over expected): 10 recorded Picks each across every Season. Ties go by Season points
    in the same direction (Busts: fewest first, since every Pick below replacement floors to the same
    value), then Season, then overall pick."""

    def picks(column: str, direction: str) -> list[dict]:
        rows = conn.execute(
            f"""SELECT year, owner, team_name, overall_pick, round, round_pick, player_name, position, nfl_team,
                       points, positional_finish, value_over_slot, points_over_expected
                FROM stats.draft_board WHERE {column} IS NOT NULL
                ORDER BY {column} {direction}, points {direction}, year, overall_pick LIMIT %s""",
            (ALL_TIME_PICKS,),
        ).fetchall()
        return [
            {
                "year": year,
                "owner": _owner_ref(owner),
                "teamName": team,
                "overall": overall,
                "round": rnd,
                "roundPick": round_pick,
                "player": {"name": name, "position": position, "nflTeam": nfl_team},
                "points": float(points),
                "positionalFinish": finish,
                "valueOverSlot": vos,
                "pointsOverExpected": poe,
            }
            for year, owner, team, overall, rnd, round_pick, name, position, nfl_team, points, finish, vos, poe in rows
        ]

    return {
        "steals": picks("value_over_slot", "DESC"),
        "hits": picks("points_over_expected", "DESC"),
        "busts": picks("points_over_expected", "ASC"),
    }


def _best_drafters(conn: Connection) -> list[dict]:
    """Every Owner who has drafted: their average Draft grade rank (lower is better), then name."""
    rows = conn.execute(
        """SELECT fo.display_name, count(*), round(avg(g.grade_rank), 2)
           FROM stats.draft_grades g JOIN stats.franchise_owner fo ON fo.franchise_id = g.franchise_id
           GROUP BY fo.owner_id, fo.display_name
           ORDER BY round(avg(g.grade_rank), 2), fo.display_name"""
    ).fetchall()
    return [{"owner": _owner_ref(name), "seasons": n, "averageRank": float(avg)} for name, n, avg in rows]


def _draft_note(draft_type: str, unrecorded: int) -> str | None:
    parts = []
    if draft_type == "offline":
        parts.append("Drafted offline and entered by hand.")
    if unrecorded:
        picks = "pick wasn't" if unrecorded == 1 else "picks weren't"
        parts.append(f"{unrecorded} {picks} recorded.")
    return " ".join(parts) or None


@dataclass(frozen=True)
class MatchupRow:
    """One core.matchups row, as the bracket and weekly results read it."""

    period: int
    weeks: list[int]
    playoff_round: str | None
    home_id: int
    away_id: int | None
    home_points: float | None
    away_points: float | None
    winner_id: int | None

    @property
    def is_bye(self) -> bool:
        return self.away_id is None

    @property
    def is_tie(self) -> bool:
        # The loader refuses unplayed Matchups, so a played one with no winner is a tie
        return not self.is_bye and self.winner_id is None


def _matchup_rows(conn: Connection, year: int, only_bracket: bool = False) -> list[MatchupRow]:
    """Matchups in ESPN's order. With only_bracket, the winners' bracket and the Third-place game."""
    where = "AND (m.bracket = 'winners' OR m.playoff_round = %s)" if only_bracket else ""
    params = (year, THIRD_PLACE) if only_bracket else (year,)
    rows = conn.execute(
        f"""SELECT m.matchup_period, m.first_week, m.last_week, m.playoff_round, m.home_franchise_id,
                   m.away_franchise_id, m.home_points, m.away_points, m.winner_franchise_id
            FROM core.matchups m JOIN core.seasons s USING (season_id)
            WHERE s.year = %s {where} ORDER BY m.matchup_period, m.matchup_id""",
        params,
    ).fetchall()
    return [
        MatchupRow(p, list(range(first, last + 1)), r, h, a, hp, ap, w) for p, first, last, r, h, a, hp, ap, w in rows
    ]


@dataclass(frozen=True)
class FranchiseInfo:
    seed: int
    owner: str
    team_name: str


def _franchises(conn: Connection, year: int) -> dict[int, FranchiseInfo]:
    """franchise_id -> seed, Owner and team name (via stats.standings, so through franchise_owners)."""
    rows = conn.execute(
        "SELECT franchise_id, playoff_seed, owner, team_name FROM stats.standings WHERE year = %s", (year,)
    ).fetchall()
    return {fid: FranchiseInfo(seed, owner, team) for fid, seed, owner, team in rows}


def _matchup_doc(row: MatchupRow, franchises: dict[int, FranchiseInfo], *, in_bracket: bool) -> dict:
    """A Matchup in the contract's shape. In the bracket, sides carry seeds, the better seed is listed
    first, and a bye shows no score (no game). In weekly results ESPN's order and bye score are kept."""
    sides = [(row.home_id, row.home_points), (row.away_id, row.away_points)]
    if in_bracket and not row.is_bye and franchises[row.away_id].seed < franchises[row.home_id].seed:
        sides.reverse()  # the better seed is listed first, whichever side ESPN called home
    (home_id, home_pts), (away_id, away_pts) = sides
    if in_bracket and row.is_bye:
        home_pts = None

    def side(fid, points):
        f = franchises[fid]
        doc = {
            "owner": _owner_ref(f.owner),
            "teamName": f.team_name,
            "score": None if points is None else float(points),
        }
        return {"seed": f.seed, **doc} if in_bracket else doc

    return {
        "home": side(home_id, home_pts),
        "away": None if row.is_bye else side(away_id, away_pts),
        "winner": None if row.is_bye or row.is_tie else ("home" if row.winner_id == home_id else "away"),
        "isTie": row.is_tie,
        "isBye": row.is_bye,
    }


def _weekly_results(conn: Connection, year: int) -> list[dict]:
    """Every Matchup period in order, each with all of its Matchups (regular season, playoffs and
    consolation games) in ESPN's order. Scores are ESPN's Matchup totals: no manual adjustments.
    A team on a bye shows the points ESPN recorded for it that Week."""
    franchises = _franchises(conn, year)
    periods: dict[int, dict] = {}
    for row in _matchup_rows(conn, year):
        p = periods.setdefault(row.period, {"matchupPeriod": row.period, "weeks": row.weeks, "matchups": []})
        p["matchups"].append(_matchup_doc(row, franchises, in_bracket=False))
    return [periods[p] for p in sorted(periods)]


# core.matchups.playoff_round -> round name shown on the site
ROUND_NAMES = {"quarterfinal": "Quarterfinals", "semifinal": "Semifinals", "final": "Championship"}


def _bracket(conn: Connection, year: int) -> dict:
    """Winners' bracket rounds plus the Third-place game. Consolation games (5th place and the
    losers' ladder) aren't part of it. Scores are ESPN's Matchup totals, so a two-week round
    shows its combined score."""
    franchises = _franchises(conn, year)
    rounds: dict[int, dict] = {}
    third = None
    for row in _matchup_rows(conn, year, only_bracket=True):
        matchup = _matchup_doc(row, franchises, in_bracket=True)
        if row.playoff_round == THIRD_PLACE:
            third = {"matchupPeriod": row.period, "weeks": row.weeks, "matchup": matchup}
            continue
        name = ROUND_NAMES.get(row.playoff_round) or (row.playoff_round or "Playoffs").title()
        rounds.setdefault(row.period, {"name": name, "matchupPeriod": row.period, "weeks": row.weeks, "matchups": []})
        rounds[row.period]["matchups"].append(matchup)
    if third is None or not rounds:
        raise ExportError(f"Season {year}: the bracket has no rounds or no Third-place game")
    final = rounds[max(rounds)]
    if len(final["matchups"]) != 1:
        raise ExportError(f"Season {year}: the championship round has {len(final['matchups'])} Matchups, not 1")
    for r in rounds.values():
        r["matchups"].sort(key=lambda m: m["home"]["seed"])
    return {"rounds": [rounds[p] for p in sorted(rounds)], "thirdPlaceGame": third}


# Display order and labels for the Scoring format tab (keys: core.seasons.scoring_rules)
KEY_VALUE_LABELS = [
    ("pass_yds", "Passing yard"),
    ("pass_td", "Passing TD"),
    ("pass_int", "Interception thrown"),
    ("rush_yds", "Rushing yard"),
    ("rush_td", "Rushing TD"),
    ("rec", "Reception"),
    ("rec_yds", "Receiving yard"),
    ("rec_td", "Receiving TD"),
    ("fum_lost", "Fumble lost"),
]
SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "OP", "D/ST", "K", "BE", "IR"]


def _scoring_format(conn: Connection, year: int) -> dict:
    label, reception, te_premium, rules, slots = conn.execute(
        "SELECT scoring_label, reception_points, te_premium, scoring_rules, roster_slots FROM core.seasons "
        "WHERE year = %s",
        (year,),
    ).fetchone()
    rules, slots = rules or {}, slots or {}
    ordered_slots = sorted(slots, key=lambda s: (SLOT_ORDER.index(s) if s in SLOT_ORDER else len(SLOT_ORDER), s))
    return {
        "label": label,
        "receptionPoints": float(reception),
        "tePremium": float(te_premium or 0),
        "keyValues": [{"label": text, "points": float(rules[key])} for key, text in KEY_VALUE_LABELS if key in rules],
        "rosterSlots": [{"slot": s, "count": slots[s]} for s in ordered_slots if slots[s]],
    }


def _standings(conn: Connection, year: int, team_count: int) -> list[dict]:
    rows = conn.execute(
        """SELECT final_rank, owner, team_name, wins, losses, ties, points_for, points_against, playoff_seed
           FROM stats.standings WHERE year = %s ORDER BY final_rank""",
        (year,),
    ).fetchall()
    if [r[0] for r in rows] != list(range(1, team_count + 1)):
        raise ExportError(f"Season {year}: final ranks should be 1..{team_count}, found {[r[0] for r in rows]}")
    return [
        {
            "rank": rank,
            "owner": _owner_ref(owner),
            "teamName": team,
            "record": _record(w, lost, tied),
            "pointsFor": float(pf),
            "pointsAgainst": float(pa),
            "playoffSeed": seed,
        }
        for rank, owner, team, w, lost, tied, pf, pa, seed in rows
    ]


def _owner_ref(name: str) -> dict:
    return {"slug": slugify(name), "name": name}


def _record(wins: int, losses: int, ties: int) -> dict:
    return {"wins": wins, "losses": losses, "ties": ties}
