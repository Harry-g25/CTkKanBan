"""Smoke-test an installed package without importing from the checkout."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from importlib.metadata import version as distribution_version
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path = [entry for entry in sys.path if entry and Path(entry).resolve() != ROOT]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wheel-dir",
        type=Path,
        help="Install the single wheel in this directory, resolving its declared dependencies",
    )
    return parser.parse_args(argv)


def install_wheel(directory: Path) -> str:
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"Expected one wheel in {directory}; found {len(wheels)}")
    wheel = wheels[0].resolve()
    with ZipFile(wheel) as archive:
        metadata_files = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise ValueError(f"{wheel.name} must contain exactly one METADATA file")
        metadata_text = archive.read(metadata_files[0]).decode("utf-8")
    version_lines = [line.removeprefix("Version: ") for line in metadata_text.splitlines() if line.startswith("Version: ")]
    if len(version_lines) != 1:
        raise ValueError(f"Could not identify the version in {wheel.name}")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--force-reinstall", str(wheel)],
        check=True,
    )
    return version_lines[0]


def main() -> None:
    args = parse_args()
    expected_version = install_wheel(args.wheel_dir) if args.wheel_dir is not None else None
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)

    import ctk_kanban
    from ctk_kanban import CardQuery, SQLiteKanbanDataSource

    package_path = Path(ctk_kanban.__file__).resolve()
    if ROOT == package_path or ROOT in package_path.parents:
        raise RuntimeError(f"Smoke test imported the source checkout: {package_path}")
    installed_version = distribution_version("ctk-kanban")
    if installed_version != ctk_kanban.__version__:
        raise RuntimeError(
            f"Distribution version {installed_version} does not match imported package {ctk_kanban.__version__}"
        )
    if expected_version is not None and installed_version != expected_version:
        raise RuntimeError(f"Installed {installed_version}, but the wheel contains {expected_version}")
    with tempfile.TemporaryDirectory() as directory:
        source = SQLiteKanbanDataSource(Path(directory) / "smoke.db")
        source.seed_board(
            "smoke",
            [{"id": "todo", "title": "To Do"}],
            [{"id": 1, "column": "todo", "title": "Installed wheel", "sort_order": 1024}],
        )
        loaded = source.load_board("smoke")
        page = source.query_cards("smoke", CardQuery(search="wheel"))
        assert loaded.cards[0]["id"] == 1
        assert page.total == 1
    print(f"Smoke-tested ctk-kanban {ctk_kanban.__version__} from {package_path}")


if __name__ == "__main__":
    main()
