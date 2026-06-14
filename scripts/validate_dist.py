"""Run every distribution check used by CI and release workflows."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--tag")
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()

    verify_args = ["scripts/verify_release.py", "--dist", str(args.dist)]
    if args.tag:
        verify_args.extend(["--tag", args.tag])
    if args.write_checksums:
        verify_args.append("--write-checksums")
    run(*verify_args)

    distributions = sorted(args.dist.glob("*.whl")) + sorted(args.dist.glob("*.tar.gz"))
    wheels = sorted(args.dist.glob("*.whl"))
    run("-m", "twine", "check", "--strict", *(str(path) for path in distributions))
    run("-m", "check_wheel_contents", *(str(path) for path in wheels))
    run("-m", "pyroma", ".")


if __name__ == "__main__":
    main()

