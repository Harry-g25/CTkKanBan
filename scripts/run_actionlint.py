"""Download a pinned, checksummed Actionlint binary and validate workflows."""

from __future__ import annotations

import hashlib
import os
import platform
import stat
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.7.12"
CHECKSUMS = {
    ("Darwin", "arm64"): "aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f",
    ("Darwin", "x86_64"): "5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644",
    ("Linux", "x86_64"): "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
    ("Windows", "AMD64"): "6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9",
}


def archive_details(system: str, machine: str) -> tuple[str, str]:
    if system == "Windows" and machine == "AMD64":
        return "windows_amd64.zip", "actionlint.exe"
    if system == "Linux" and machine == "x86_64":
        return "linux_amd64.tar.gz", "actionlint"
    if system == "Darwin" and machine in {"x86_64", "arm64"}:
        return f"darwin_{'amd64' if machine == 'x86_64' else 'arm64'}.tar.gz", "actionlint"
    raise RuntimeError(f"Unsupported Actionlint platform: {system} {machine}")


def safe_tar_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"Unsafe Actionlint archive member: {member.name}")
    return members


def install_actionlint() -> Path:
    system = platform.system()
    machine = platform.machine()
    suffix, binary_name = archive_details(system, machine)
    expected = CHECKSUMS[(system, machine)]
    tool_dir = ROOT / ".tools" / "actionlint" / f"v{VERSION}"
    binary = tool_dir / binary_name
    if binary.exists():
        return binary

    tool_dir.mkdir(parents=True, exist_ok=True)
    archive_path = tool_dir / f"actionlint_{VERSION}_{suffix}"
    url = f"https://github.com/rhysd/actionlint/releases/download/v{VERSION}/{archive_path.name}"
    urllib.request.urlretrieve(url, archive_path)
    actual = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if actual != expected:
        archive_path.unlink(missing_ok=True)
        raise RuntimeError(f"Actionlint checksum mismatch: expected {expected}, got {actual}")

    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extract(binary_name, tool_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(tool_dir, members=safe_tar_members(archive))
    archive_path.unlink()
    if system != "Windows":
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return binary


def main() -> None:
    binary = install_actionlint()
    environment = os.environ.copy()
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    subprocess.run([str(binary), *(str(path) for path in workflows)], check=True, env=environment)
    print(f"Actionlint v{VERSION} validated GitHub Actions workflows")


if __name__ == "__main__":
    main()

