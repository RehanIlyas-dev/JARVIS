#!/usr/bin/env python3
"""
Unit tests for jarvis/config.py — verify all constants are correct.
"""

from jarvis import config


def test_max_agentic_iterations():
    assert config.MAX_AGENTIC_ITERATIONS == 8


def test_stt_fail_threshold():
    assert config.STT_FAIL_THRESHOLD == 4


def test_active_secs():
    assert config.ACTIVE_SECS == 30


def test_history_limit():
    assert config.HISTORY_LIMIT == 40


def test_context_window():
    assert config.CONTEXT_WINDOW == 10


def test_flask_host():
    assert config.FLASK_HOST == "127.0.0.1"


def test_flask_port():
    assert config.FLASK_PORT == 5000


def test_all_constants_are_defined():
    """Ensure we didn't forget to check any constant."""
    expected = {
        "MAX_AGENTIC_ITERATIONS": 8,
        "STT_FAIL_THRESHOLD": 4,
        "ACTIVE_SECS": 30,
        "HISTORY_LIMIT": 40,
        "CONTEXT_WINDOW": 10,
        "FLASK_HOST": "127.0.0.1",
        "FLASK_PORT": 5000,
    }
    for name, value in expected.items():
        assert getattr(config, name, object()) == value, f"{name} mismatch"


def test_constants_are_integers_and_strings():
    """Verify type correctness for constants."""
    assert isinstance(config.MAX_AGENTIC_ITERATIONS, int)
    assert isinstance(config.STT_FAIL_THRESHOLD, int)
    assert isinstance(config.ACTIVE_SECS, int)
    assert isinstance(config.HISTORY_LIMIT, int)
    assert isinstance(config.CONTEXT_WINDOW, int)
    assert isinstance(config.FLASK_HOST, str)
    assert isinstance(config.FLASK_PORT, int)
