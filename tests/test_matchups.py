"""Seam 1 for the Matchups section (#36). All data is invented.

Fixture playoff rule (tests/espn_fixture.py): the better seed wins every playoff Matchup unless the
other side is in `upsets`; the winner scores 120.5 at home or 118.0 away, the loser 101.25 or 99.75.
"""

import json

from espn_fixture import Season2018Style, team
from test_build import SEED_ORDER, season
from test_draft import owner

from washingwood.build import build
from washingwood.contract import validate


def side(key, seed, score):
    from espn_fixture import PEOPLE

    return {"seed": seed, "owner": owner(key), "teamName": PEOPLE[key][1], "score": score}


def test_championship_cards_list_every_final_newest_first(archive, owners, tmp_path, pg_dsn):
    # 2018 style: two-week final (period 15 = Weeks 16-17), seed 1 Quinn beats seed 2 Pell at home.
    Season2018Style(2018, [team(k) for k in SEED_ORDER[:10]]).write(archive)
    # 2020 style: seed 5 Tamsin wins every round as the away side and beats seed 2 Pell in the final.
    season(2020, upsets={"tamsin"}).write(archive)
    out = tmp_path / "export"
    build(archive_dir=archive, owners_file=owners, out_dir=out, dsn=pg_dsn)
    doc = json.loads((out / "matchups.json").read_text(encoding="utf-8"))
    validate(doc, "matchups")

    assert doc["championships"] == [
        {
            "year": 2020,
            "matchupPeriod": 17,
            "weeks": [17],
            "champion": side("tamsin", 5, 118.0),
            "runnerUp": side("pell", 2, 99.75),
            "margin": 18.25,
        },
        {
            "year": 2018,
            "matchupPeriod": 15,
            "weeks": [16, 17],
            "champion": side("quinn", 1, 120.5),
            "runnerUp": side("pell", 2, 101.25),
            "margin": 19.25,
        },
    ]
