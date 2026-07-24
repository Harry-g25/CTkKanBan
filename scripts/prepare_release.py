"""Update the package version and move Unreleased notes into a dated release."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
DOCS_VERSION_PATTERN = re.compile(r'(<span class="nav-version">)v[^<]+ Docs(</span>)')


def update_docs_version(document: str, version: str) -> str:
    """Return the documentation page with its visible release version updated."""

    if len(DOCS_VERSION_PATTERN.findall(document)) != 1:
        raise ValueError("docs/index.html must contain exactly one version badge")
    return DOCS_VERSION_PATTERN.sub(rf"\g<1>v{version} Docs\g<2>", document, count=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", help="PEP 440 release version, for example 0.3.0")
    args = parser.parse_args()
    version = str(Version(args.version))
    if Version(version).is_devrelease or Version(version).is_prerelease:
        raise ValueError("prepare_release expects a final release version")

    version_file = ROOT / "ctk_kanban" / "version.py"
    version_text = version_file.read_text(encoding="utf-8")
    updated_version, count = re.subn(
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{version}"',
        version_text,
        count=1,
    )
    if count != 1:
        raise ValueError("Could not update ctk_kanban/version.py")

    changelog_path = ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    match = re.search(r"^## Unreleased\s*\n(?P<body>.*?)(?=^## |\Z)", changelog, re.MULTILINE | re.DOTALL)
    if match is None or not match.group("body").strip():
        raise ValueError("Add release notes under '## Unreleased' before preparing a release")
    if re.search(rf"^## {re.escape(version)}(?:\s|$)", changelog, re.MULTILINE):
        raise ValueError(f"CHANGELOG.md already contains {version}")
    release_section = f"## Unreleased\n\n## {version} - {date.today().isoformat()}\n\n{match.group('body').strip()}\n\n"
    updated_changelog = changelog[: match.start()] + release_section + changelog[match.end() :].lstrip()

    docs_path = ROOT / "docs" / "index.html"
    updated_docs = update_docs_version(docs_path.read_text(encoding="utf-8"), version)

    version_file.write_text(updated_version, encoding="utf-8", newline="\n")
    changelog_path.write_text(updated_changelog, encoding="utf-8", newline="\n")
    docs_path.write_text(updated_docs, encoding="utf-8", newline="\n")
    print(f"Prepared {version}. Run tox, commit, then tag v{version}.")


if __name__ == "__main__":
    main()
