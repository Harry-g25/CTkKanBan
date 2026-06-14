"""Validate release identity and the contents of built distributions."""

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath

from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "ctk-kanban"


def project_version() -> str:
    version_file = ROOT / "ctk_kanban" / "version.py"
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', version_file.read_text(), re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not read __version__ from {version_file}")
    return str(Version(match.group(1)))


def validate_release_identity(version: str, tag: str | None) -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if re.search(rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE) is None:
        raise ValueError(f"CHANGELOG.md has no dated section for {version}")
    if tag and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match package version v{version}")


def validate_member_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Distribution contains unsafe path: {name}")


def validate_wheel(path: Path, version: str) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            validate_member_path(name)
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError(f"{path.name} must contain exactly one METADATA file")
        metadata = BytesParser(policy=default).parsebytes(archive.read(metadata_names[0]))
        if canonicalize_name(metadata["Name"]) != canonicalize_name(PACKAGE_NAME):
            raise ValueError(f"Unexpected wheel project name: {metadata['Name']}")
        if metadata["Version"] != version:
            raise ValueError(f"Wheel version {metadata['Version']} does not match {version}")
        if metadata["Requires-Python"] != ">=3.10":
            raise ValueError("Wheel must declare Requires-Python: >=3.10")
        if metadata["License-Expression"] != "MIT":
            raise ValueError("Wheel must declare the MIT license expression")
        if "ctk_kanban/py.typed" not in names:
            raise ValueError("Wheel is missing ctk_kanban/py.typed")


def validate_sdist(path: Path, version: str) -> None:
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
        for name in names:
            validate_member_path(name)
    required_suffixes = {
        "CHANGELOG.md",
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "ctk_kanban/py.typed",
        "ctk_kanban/version.py",
        "scripts/verify_release.py",
    }
    present = {suffix for suffix in required_suffixes if any(name.endswith(suffix) for name in names)}
    missing = required_suffixes - present
    if missing:
        raise ValueError(f"Source distribution is missing: {', '.join(sorted(missing))}")
    expected_fragment = version.replace("-", "_")
    if expected_fragment not in path.name:
        raise ValueError(f"Source distribution filename does not contain version {version}")


def write_checksums(paths: list[Path], destination: Path) -> None:
    lines = []
    for path in sorted(paths, key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    destination.write_text("\n".join(lines) + "\n", encoding="ascii")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--tag")
    parser.add_argument("--write-checksums", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    version = project_version()
    validate_release_identity(version, args.tag)
    wheels = sorted(args.dist.glob("*.whl"))
    sdists = sorted(args.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError(f"Expected one wheel and one sdist in {args.dist}; found {len(wheels)} and {len(sdists)}")
    validate_wheel(wheels[0], version)
    validate_sdist(sdists[0], version)
    if args.write_checksums:
        write_checksums([wheels[0], sdists[0]], args.dist / "SHA256SUMS")
    print(f"Validated {PACKAGE_NAME} {version}: {wheels[0].name}, {sdists[0].name}")


if __name__ == "__main__":
    main()
