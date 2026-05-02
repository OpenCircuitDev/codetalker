"""Tests for CadenceStrategy base class."""
import pytest
from claude_code_talker.cadence.base import CadenceStrategy, Decision


def test_decision_default_no_fire():
    d = Decision()
    assert d.fire_immediately is False
    assert d.fire_periodic is False
    assert d.events == []


def test_cadence_subclass_must_set_name():
    with pytest.raises(TypeError):
        class Bad(CadenceStrategy):
            def on_event(self, e): return Decision()
            def tick(self): return Decision()
        Bad()  # name == "base" — should raise via __init_subclass__
