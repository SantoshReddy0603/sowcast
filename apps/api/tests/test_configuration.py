import os

import pytest

from sowcast.configuration import load_environment


def test_environment_file_overrides_only_declared_values(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "old-test-credential")
    monkeypatch.setenv("GEMINI_MODEL", "existing-model")
    path = tmp_path / "local.env"
    path.write_text(
        '\ufeff# local configuration\n\n GEMINI_API_KEY = "new-test-credential"\n'
        "SOWCAST_TEST_CONFIG='literal $value=with#characters'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SOWCAST_TEST_CONFIG", raising=False)
    load_environment(path)
    assert os.environ["GEMINI_API_KEY"] == "new-test-credential"
    assert os.environ["GEMINI_MODEL"] == "existing-model"
    assert os.environ["SOWCAST_TEST_CONFIG"] == "literal $value=with#characters"
    monkeypatch.delenv("SOWCAST_TEST_CONFIG")


@pytest.mark.parametrize(
    "invalid",
    [
        "missing-separator",
        "INVALID NAME=private-value",
        "GEMINI_API_KEY='private-value",
        "GEMINI_API_KEY=first\nGEMINI_API_KEY=private-value",
    ],
)
def test_invalid_file_does_not_apply_partial_configuration(tmp_path, monkeypatch, invalid):
    monkeypatch.setenv("GEMINI_MODEL", "existing-model")
    path = tmp_path / "local.env"
    path.write_text("GEMINI_MODEL=replacement\n" + invalid, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_environment(path)
    assert "private-value" not in str(error.value)
    assert os.environ["GEMINI_MODEL"] == "existing-model"
