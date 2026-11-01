"""Build a source ZIP without local credentials, databases or dependencies."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    "node_modules",
    ".venv",
    ".git",
    ".sowcast",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".npm-cache",
    "dist",
    "build",
    "test-results",
    "release",
    ".recording",
}
TOP = {
    "apps",
    "docs",
    "scripts",
    ".github",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    "README.md",
    "docker-compose.yml",
    "render.yaml",
}


def build(destination: Path) -> dict:
    if destination.resolve().is_relative_to(ROOT):
        raise ValueError("Archive destination must be outside the checkout")
    secrets = [
        value.encode()
        for name in (
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "DATA_GOV_IN_API_KEY",
            "AGMARKNET_API_KEY",
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
        )
        if len(value := os.environ.get(name, "").strip()) >= 8
    ]
    files = []
    for folder, directories, names in os.walk(ROOT, followlinks=False):
        base = Path(folder)
        directories[:] = sorted(
            name
            for name in directories
            if name not in SKIP
            and not name.endswith(".egg-info")
            and not (base / name).is_symlink()
            and (base != ROOT or name in TOP)
        )
        for name in sorted(names):
            file = base / name
            if base == ROOT and name not in TOP:
                continue
            if (
                file.is_symlink()
                or file.suffix in {".pyc", ".log"}
                or re.search(r"\.(?:sqlite3?|db)(?:-(?:wal|shm|journal))?$", name, re.I)
            ):
                continue
            if name.startswith(".env") and name != ".env.example":
                continue
            data = file.read_bytes()
            if any(secret in data for secret in secrets):
                raise ValueError("Configured secret found; no archive was created")
            files.append((file.relative_to(ROOT).as_posix(), data))
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        destination.open("xb") as stream,
        ZipFile(stream, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive,
    ):
        for name, data in files:
            archive.writestr("Sowcast/" + name, data)
        archive.writestr("Sowcast/RELEASE-MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    return {
        "files": len(files),
        "bytes": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "configured_secret_scan": "passed",
        "private_runtime_data": "excluded",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New ZIP path; never overwrites")
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), indent=2))
