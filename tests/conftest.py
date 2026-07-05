from pathlib import Path

import pytest

from config.settings import load_league_settings
from data.models import Position
from engine.replacement import PlayerValue

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_league():
    """4-team league: QB/RB/WR/FLEX(RB,WR,TE) starters, 2 bench. See fixtures/test_league.yaml."""
    return load_league_settings(FIXTURES / "test_league.yaml")


@pytest.fixture
def sample_player_values() -> list[PlayerValue]:
    """A hand-picked pool whose effective-starter/replacement math is worked out by hand
    in tests/test_replacement.py's module docstring-equivalent comments."""
    values = []
    for i, v in enumerate([100, 90, 80, 70, 60, 50]):
        values.append(PlayerValue(player_id=f"qb{i}", position=Position.QB, value=v))
    for i, v in enumerate([120, 110, 100, 90, 80, 70, 60]):
        values.append(PlayerValue(player_id=f"rb{i}", position=Position.RB, value=v))
    for i, v in enumerate([115, 105, 95, 85, 75, 65, 55]):
        values.append(PlayerValue(player_id=f"wr{i}", position=Position.WR, value=v))
    for i, v in enumerate([90, 50, 40, 30]):
        values.append(PlayerValue(player_id=f"te{i}", position=Position.TE, value=v))
    return values
