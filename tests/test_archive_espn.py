import datetime as dt
import importlib.util
from pathlib import Path

# scripts/ is not a package, so load the module by path
_spec = importlib.util.spec_from_file_location(
    "archive_espn", Path(__file__).parent.parent / "scripts" / "archive_espn.py"
)
archive_espn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(archive_espn)


def test_current_season_rolls_over_in_august():
    assert archive_espn.current_season(dt.date(2026, 7, 31)) == 2025
    assert archive_espn.current_season(dt.date(2026, 8, 1)) == 2026


def test_parse_years_accepts_ranges_and_lists():
    assert archive_espn.parse_years("2017-2019,2021") == [2017, 2018, 2019, 2021]
