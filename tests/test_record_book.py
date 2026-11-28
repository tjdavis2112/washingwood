"""Seam 1 for the Record Book (#49). All data is invented.

Fixture rule (tests/espn_fixture.py): seed s finishes (regular periods - s) wins and s losses, with
1500 - s points for, so the last seed in the team order is Last place.
"""

import json

from espn_fixture import PEOPLE, Season2018Style, team
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate


def record_book(archive, owners, tmp_path, pg_dsn) -> dict:
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "record-book.json").read_text(encoding="utf-8"))
    validate(doc, "recordBook")
    return doc


def last(key, year, wins, losses, points_for, scoring):
    return {
        "year": year,
        "owner": owner(key),
        "teamName": PEOPLE[key][1],
        "record": {"wins": wins, "losses": losses, "ties": 0},
        "pointsFor": points_for,
        "scoringFormat": scoring,
    }


def test_last_place_history_and_tally(archive, owners, tmp_path, pg_dsn):
    # 2018 style (10 teams, 13 regular periods): Jory is seed 10, the worst regular season
    Season2018Style(2018, [team(k) for k in SEED_ORDER[2:12]]).write(archive)
    # 2020 style (12 teams, 14 regular periods): Jory last again, with a TE premium
    season(2020, te_premium=True).write(archive)
    # 2021: Cass and Jory swap, so Cass is last
    season(2021, order=[*SEED_ORDER[:10], "jory", "cass"]).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    assert doc["lastPlace"]["seasons"] == [
        last("cass", 2021, 2, 12, 1488.0, "PPR"),
        last("jory", 2020, 2, 12, 1488.0, "PPR + TE premium"),
        last("jory", 2018, 3, 10, 1490.0, "PPR"),
    ]
    # Count descending, then name; Seasons oldest first
    assert doc["lastPlace"]["tally"] == [
        {"owner": owner("jory"), "count": 2, "years": [2018, 2020]},
        {"owner": owner("cass"), "count": 1, "years": [2021]},
    ]


def test_tally_ties_are_ordered_by_name(archive, owners, tmp_path, pg_dsn):
    season(2020).write(archive)
    season(2021, order=[*SEED_ORDER[:10], "jory", "cass"]).write(archive)

    tally = record_book(archive, owners, tmp_path, pg_dsn)["lastPlace"]["tally"]

    names = [e["owner"]["name"] for e in tally]
    assert names == sorted(names)
    assert [e["count"] for e in tally] == [1, 1]


def test_season_records_rank_points_per_game_not_total(archive, owners, tmp_path, pg_dsn):
    # 2018 (13 games): Quinn scores 1499. 2020 (14 games): a +50 adjustment makes Quinn's total
    # 1549, the highest, but only 110.64 per game
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    season(2020, adjustments={"quinn": 50.0}).write(archive)

    season_doc = record_book(archive, owners, tmp_path, pg_dsn)["season"]

    top = season_doc["mostPointsFor"]
    # Every 2018 Franchise (lowest 1490 / 13 = 114.62) out-scores 2020 Quinn per game, so the season
    # with the highest total (1549) misses the top 10
    assert [r["year"] for r in top] == [2018] * 10
    assert (top[0]["owner"]["slug"], top[0]["pointsFor"], top[0]["games"], top[0]["pointsPerGame"]) == (
        "quinn-harrow",
        1499.0,
        13,
        115.31,
    )
    assert season_doc["fewestPointsFor"][0]["pointsPerGame"] == round(1488 / 14, 2)  # Jory, 2020
    assert season_doc["mostPointsAgainst"][0]["pointsAgainstPerGame"] == round(1410 / 13, 2)  # Wren, 2018
    assert all(len(v) == 10 for v in season_doc.values())


def test_playoff_and_consolation_games_do_not_count(archive, owners, tmp_path, pg_dsn):
    # Quinn (seed 1) plays playoff Matchups, Jory (seed 12) consolation ones; neither adds games
    season(2020).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    best = doc["season"]["bestWinPct"][0]
    assert (best["owner"]["slug"], best["record"], best["games"], best["winPct"]) == (
        "quinn-harrow",
        {"wins": 13, "losses": 1, "ties": 0},
        14,
        0.9286,
    )
    assert doc["season"]["worstWinPct"][0]["owner"]["slug"] == "jory-paxton"
    assert {r["games"] for r in doc["allTime"]} == {14}


def test_all_time_includes_owners_who_left(archive, owners, tmp_path, pg_dsn):
    # Nell is seed 10 (last) in 2018 and gone by 2020
    Season2018Style(2018, [team(k) for k in [*SEED_ORDER[:9], "nell"]]).write(archive)
    season(2020).write(archive)

    all_time = record_book(archive, owners, tmp_path, pg_dsn)["allTime"]

    assert len(all_time) == 13
    (nell,) = [r for r in all_time if r["owner"] == owner("nell")]
    assert nell == {
        "owner": owner("nell"),
        "seasons": 1,
        "record": {"wins": 3, "losses": 10, "ties": 0},
        "games": 13,
        "winPct": 0.2308,
        "pointsFor": 1490.0,
        "pointsPerGame": 114.62,
        "benchPoints": 351.0,  # 13 Weeks x 27.0
        "luck": -3.8,  # 3 wins, from the fixture's round-robin schedule
        "longestWinStreak": 4,  # from the fixture's round-robin schedule
        "longestLossStreak": 5,
        "lastPlaces": 1,
    }
    (quinn,) = [r for r in all_time if r["owner"] == owner("quinn")]
    assert (quinn["seasons"], quinn["record"]["wins"], quinn["games"], quinn["pointsFor"]) == (2, 25, 27, 2998.0)
    assert (quinn["winPct"], quinn["pointsPerGame"], quinn["lastPlaces"]) == (0.9259, 111.04, 0)
    # Wins descending, then name
    assert [r["record"]["wins"] for r in all_time] == sorted((r["record"]["wins"] for r in all_time), reverse=True)


def test_season_record_ties_go_to_the_earlier_season_then_name(archive, owners, tmp_path, pg_dsn):
    # Two identical Seasons, and a +1 adjustment puts Pell level with Quinn (1499) in each
    season(2020, adjustments={"pell": 1.0}).write(archive)
    season(2021, adjustments={"pell": 1.0}).write(archive)

    top = record_book(archive, owners, tmp_path, pg_dsn)["season"]["mostPointsFor"][:4]

    assert [(r["year"], r["owner"]["slug"]) for r in top] == [
        (2020, "pell-vantor"),
        (2020, "quinn-harrow"),
        (2021, "pell-vantor"),
        (2021, "quinn-harrow"),
    ]


# Bench points (#52). Fixture rule: each bench (BE) Player scores 4.5 and the IR Player 4.5, so a side's
# Bench points are 6 x 4.5 = 27.0 a Week unless bench_bonus or bench_unplayed changes them.


def test_bench_points_skip_ir_count_an_unplayed_player_as_zero_and_season_totals_are_regular_only(
    archive, owners, tmp_path, pg_dsn
):
    # Quinn (seed 1): +20 in regular Week 3, +100 in the Week 16 semifinal. Pell's 2nd bench Player
    # didn't play in Week 5 (NULL points)
    season(2020, bench_bonus={(3, "quinn"): 20.0, (16, "quinn"): 100.0}, bench_unplayed=(5, "pell")).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    top = doc["week"]["mostBenchPoints"]
    assert [(r["week"], r["kind"], r["team"]["owner"]["slug"], r["benchPoints"]) for r in top[:2]] == [
        (16, "playoff", "quinn-harrow", 127.0),
        (3, "regular", "quinn-harrow", 47.0),
    ]
    # Season Bench points: 14 regular Weeks x 27.0 = 378.0; the semifinal's 100 doesn't count
    season_bench = {r["owner"]["slug"]: r["benchPoints"] for r in doc["season"]["mostBenchPoints"]}
    assert season_bench["quinn-harrow"] == 398.0
    assert doc["season"]["mostBenchPoints"][0]["owner"] == owner("quinn")
    all_time = {r["owner"]["slug"]: r["benchPoints"] for r in doc["allTime"]}
    assert all_time["quinn-harrow"] == 398.0
    assert all_time["pell-vantor"] == 378.0 - 4.5  # the unplayed bench Player counts 0
    assert all_time["odie-brask"] == 378.0


def test_week_records_skip_two_week_rounds_the_third_place_game_and_consolation_games(
    archive, owners, tmp_path, pg_dsn
):
    # Big bench Weeks that aren't Counted Matchups: a 2018 two-week semifinal (Quinn, Week 14), a 2020
    # consolation game (Jory, seed 12, Week 15) and the 2020 Third-place game (Rue, seed 4, Week 17)
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]], bench_bonus={(14, "quinn"): 200.0}).write(archive)
    season(2020, bench_bonus={(15, "jory"): 200.0, (17, "rue"): 200.0, (2, "abel"): 10.0}).write(archive)

    week = record_book(archive, owners, tmp_path, pg_dsn)["week"]

    top = week["mostBenchPoints"][0]
    assert (top["year"], top["week"], top["team"]["owner"]["slug"], top["benchPoints"]) == (2020, 2, "abel-trice", 37.0)
    assert all(r["benchPoints"] < 100 for r in week["mostBenchPoints"])
    for rows in week.values():
        assert all(not (r["year"] == 2018 and r["week"] >= 14) for r in rows)


def test_a_tied_matchup_is_neither_a_win_nor_a_loss(archive, owners, tmp_path, pg_dsn):
    # Period 2's first Matchup ends 110.0-110.0: above every losing score (101.25) and below every
    # winning one (120.5), so it would top both lists if it counted
    season(2020, tie_period=2).write(archive)

    week = record_book(archive, owners, tmp_path, pg_dsn)["week"]

    assert {(r["result"], r["team"]["score"]) for r in week["mostPointsInLoss"]} == {("loss", 101.25)}
    assert {(r["result"], r["team"]["score"]) for r in week["fewestPointsInWin"]} == {("win", 120.5)}
    # Ties in the ranking: earlier Week, then Owner name
    keys = [(r["week"], r["team"]["owner"]["name"]) for r in week["mostPointsInLoss"]]
    assert keys == sorted(keys)


# Streaks (#53). Fixture rule (tests/espn_fixture.py): the regular season is a round robin in which the
# first team in the order is always home and the home team always wins, so seed 1 wins every regular-season
# game and plays playoff games too.


def streak(key, length, start, end, active):
    return {
        "owner": owner(key),
        "length": length,
        "start": {"year": start[0], "week": start[1]},
        "end": {"year": end[0], "week": end[1]},
        "active": active,
    }


def test_a_streak_carries_across_seasons_and_through_a_skipped_season(archive, owners, tmp_path, pg_dsn):
    # Quinn wins all 13 regular-season games in 2018, sits out 2019, then wins all 14 in 2020. Quinn's
    # 2018 playoff wins don't extend it: 13 + 14 = 27
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    Season2018Style(2019, [team(k) for k in SEED_ORDER[2:12]]).write(archive)
    season(2020).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    assert doc["streaks"]["wins"][0] == streak("quinn", 27, (2018, 1), (2020, 14), True)
    (quinn,) = [r for r in doc["allTime"] if r["owner"] == owner("quinn")]
    assert (quinn["longestWinStreak"], quinn["longestLossStreak"]) == (27, 0)
    assert all(len(v) <= 10 for v in doc["streaks"].values())


def test_a_tie_ends_a_streak_and_only_runs_into_the_latest_season_are_active(archive, owners, tmp_path, pg_dsn):
    # Quinn's period-5 Matchup (the first one) is a tie in 2020: 4 wins, the tie, then 9 + 14 wins.
    # Jory plays 2020 but not 2021, so no Streak of Jory's can be active
    season(2020, tie_period=5).write(archive)
    season(2021, order=[*SEED_ORDER[:11], "nell"]).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    assert doc["streaks"]["wins"][0] == streak("quinn", 23, (2020, 6), (2021, 14), True)
    (quinn,) = [r for r in doc["allTime"] if r["owner"] == owner("quinn")]
    assert quinn["longestWinStreak"] == 23
    rows = doc["streaks"]["wins"] + doc["streaks"]["losses"]
    assert all(r["end"] == {"year": 2021, "week": 14} for r in rows if r["active"])
    assert not any(r["active"] for r in rows if r["owner"] == owner("jory"))
    # Equal lengths: earlier start Season, then Week, then Owner name
    for kind in ("wins", "losses"):
        keys = [
            (-r["length"], r["start"]["year"], r["start"]["week"], r["owner"]["name"]) for r in doc["streaks"][kind]
        ]
        assert keys == sorted(keys)


# Luck index (#54). Fixture rule: every regular-season Week the home sides all score 120.5 and the away
# sides 101.25, and the first team in the order (Quinn) is always home. So each Week Quinn outscores
# every away side and ties every other home side.


def test_luck_index_uses_all_play_with_half_ties_and_the_week_s_divisor(archive, owners, tmp_path, pg_dsn):
    # 2018 (10 teams): Quinn beats 5, ties 4 -> (5 + 4/2) / 9 = 7/9 a Week; 13 games -> 10.11 Expected
    # wins; 12 actual wins -> Luck 1.9.
    # 2020 (12 teams): beats 6, ties 5 -> (6 + 5/2) / 11 = 8.5/11; 14 games -> 10.82; 13 wins -> Luck 2.2.
    # Playoff and consolation Weeks don't count: Quinn's Week-15 bye (110.25) would be 5.5/11 and pull
    # Expected wins down
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    season(2020).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    rows = {(r["year"], r["owner"]["slug"]): r for v in doc["season"].values() for r in v}
    q18, q20 = rows[(2018, "quinn-harrow")], rows[(2020, "quinn-harrow")]
    assert (q18["record"]["wins"], q18["expectedWins"], q18["luck"]) == (12, 10.11, 1.9)
    assert (q20["record"]["wins"], q20["expectedWins"], q20["luck"]) == (13, 10.82, 2.2)
    # All-time sums the Seasons
    (quinn,) = [r for r in doc["allTime"] if r["owner"] == owner("quinn")]
    assert quinn["luck"] == 4.1
    # Luckiest highest first, unluckiest lowest first; ties by Season, then Owner name
    lucky = [(-r["luck"], r["year"], r["owner"]["name"]) for r in doc["season"]["luckiest"]]
    unlucky = [(r["luck"], r["year"], r["owner"]["name"]) for r in doc["season"]["unluckiest"]]
    assert lucky == sorted(lucky) and unlucky == sorted(unlucky)


def test_a_tied_weekly_score_counts_half_for_both_teams(archive, owners, tmp_path, pg_dsn):
    # Week 2's first Matchup (Quinn at home) ends 110.0-110.0. That Week Quinn beats the 5 other away sides,
    # ties the opponent and loses to the 5 other home sides: 5.5/11. Every other Week 8.5/11.
    # Expected wins = (13 x 8.5 + 5.5) / 11 = 10.55 (10.5 if the tie counted 0, 10.59 if it counted 1)
    season(2020, tie_period=2).write(archive)

    doc = record_book(archive, owners, tmp_path, pg_dsn)

    rows = {r["owner"]["slug"]: r for v in doc["season"].values() for r in v}
    assert rows["quinn-harrow"]["expectedWins"] == 10.55
