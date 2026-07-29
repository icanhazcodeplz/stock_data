"""Credentials must resolve lazily: importing ``settings`` (for
``REPO_ROOT``) has to work even when no Alpaca variables are set."""

import pytest

from settings import ENV


def test_reads_value_from_environment(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY", "test-key")
    assert ENV.ALPACA_KEY == "test-key"


def test_missing_variable_raises_with_guidance(monkeypatch):
    monkeypatch.delenv("ALPACA_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ALPACA_KEY is not set"):
        _ = ENV.ALPACA_KEY
