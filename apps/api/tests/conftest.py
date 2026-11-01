import pytest


@pytest.fixture(autouse=True)
def isolated_agent_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOWCAST_UNAVAILABLE_SOURCE", raising=False)
    monkeypatch.delenv("SOWCAST_ENV", raising=False)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOWCAST_TRACE_DB", str(tmp_path / "traces.sqlite3"))

    monkeypatch.setenv("SOWCAST_BACKTEST_DB", str(tmp_path / "backtest.sqlite3"))
