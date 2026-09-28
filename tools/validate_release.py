from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "name": "astrbot_plugin_music_selfhosted",
    "version": "1.0.0",
    "author": "beimuyira",
    "repo": "https://github.com/beimuyira/astrbot_plugin_music_selfhosted",
}
REQUIRED_FILES = {
    "_conf_schema.json",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE.md",
    "README.md",
    "SECURITY.md",
    "logo.png",
    "main.py",
    "metadata.yaml",
    "requirements.txt",
    "core/config.py",
    "core/downloader.py",
    "core/model.py",
    "core/routing.py",
    "core/sender.py",
    "core/platform/base.py",
    "core/platform/ncm_nodejs.py",
    "core/platform/qq.py",
}
SENSITIVE_FILENAMES = {"accounts.toml", ".env"}
SECRET_PATTERNS = (
    re.compile(r"\b(?:MUSIC_U|NETEASE_COOKIE|QQ_COOKIE)\s*=\s*[A-Za-z0-9+/=_-]{80,}", re.I),
    re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}", re.I),
)


def fail(message: str) -> None:
    raise AssertionError(message)


def read_metadata() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-z_]+):\s*(.*?)\s*", line)
        if match:
            values[match.group(1)] = match.group(2).strip('"\'')
    return values


def validate_metadata() -> None:
    metadata = read_metadata()
    for key, expected in EXPECTED.items():
        if metadata.get(key) != expected:
            fail(f"metadata.yaml {key!r} must be {expected!r}")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", metadata["version"]):
        fail("metadata.yaml version must use semantic versioning without a v prefix")


def validate_files() -> None:
    present = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    }
    missing = REQUIRED_FILES - present
    if missing:
        fail(f"missing release files: {sorted(missing)}")
    forbidden_artifacts = [
        path
        for path in present
        if "__pycache__" in path
        or path.endswith((".pyc", ".pyo", ".zip"))
        or path.startswith("fonts/")
        or Path(path).name in SENSITIVE_FILENAMES
        or Path(path).name.startswith(".env.")
    ]
    if forbidden_artifacts:
        fail(f"forbidden generated or unused files: {forbidden_artifacts}")
    total_size = sum(
        path.stat().st_size
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    )
    if total_size >= 16 * 1024 * 1024:
        fail("repository content must remain below the AstrBot 16 MiB package limit")


def validate_python() -> None:
    for path in ROOT.rglob("*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            fail(f"syntax error in {path.relative_to(ROOT)}: {exc}")


def validate_schema() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    required_keys = {
        "default_platform",
        "qq_api_base_url",
        "qq_quality",
        "netease_api_base_url",
        "netease_quality",
        "quality_fallback",
        "send_cover",
        "send_modes",
    }
    missing = required_keys - schema.keys()
    if missing:
        fail(f"configuration schema is missing: {sorted(missing)}")


def validate_privacy() -> None:
    text_extensions = {".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.relative_to(ROOT).parts
            or path.suffix.lower() not in text_extensions
        ):
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            fail(f"possible credential found in {path.relative_to(ROOT)}")


def main() -> int:
    validate_metadata()
    validate_files()
    validate_python()
    validate_schema()
    validate_privacy()
    print("release validation: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError) as exc:
        print(f"release validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
