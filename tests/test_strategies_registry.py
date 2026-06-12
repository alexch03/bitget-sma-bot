import pytest

from src.strategies import STRATEGIES, Strategy, make_strategy
from src.strategies.sma_crossover import SMACrossover


def test_unknown_name_raises():
    with pytest.raises(ValueError):
        make_strategy("does_not_exist")


def test_make_sma_crossover_with_params():
    strat = make_strategy("sma_crossover", fast=5, slow=20)
    assert isinstance(strat, SMACrossover)
    assert strat.fast == 5
    assert strat.slow == 20


def test_every_registered_strategy_instantiates_with_defaults():
    for name, cls in STRATEGIES.items():
        strat = make_strategy(name)
        assert isinstance(strat, Strategy)
        assert strat.name == name
        assert strat.warmup() > 0
