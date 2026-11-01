import importlib.util
from pathlib import Path
from zipfile import ZipFile


def test_source_archive_excludes_database_sidecars(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[3] / "scripts/make_release.py"
    spec = importlib.util.spec_from_file_location("release_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source"
    files = source / "apps/api"
    files.mkdir(parents=True)
    (files / "pyproject.toml").write_text("[project]\nname = 'example'\n")
    for base in ("traces.sqlite3", "traces.sqlite", "traces.db"):
        for suffix in ("", "-wal", "-shm", "-journal"):
            (files / (base + suffix)).write_bytes(b"private database fixture")
    monkeypatch.setattr(module, "ROOT", source)
    result = module.build(tmp_path / "source.zip")
    with ZipFile(tmp_path / "source.zip") as archive:
        assert set(archive.namelist()) == {
            "Sowcast/apps/api/pyproject.toml",
            "Sowcast/RELEASE-MANIFEST.json",
        }
    assert result["private_runtime_data"] == "excluded"
