"""Install declarative Skill dependencies inside a disposable build container."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


SOURCE = Path("/skill")
BUILD = Path("/tmp/movo-skill-build")
APT_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?(?:=[a-z0-9:~+._-]+)?$")


def apt_packages(path: Path) -> list[str]:
    packages = [line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines()]
    packages = [name for name in packages if name]
    if len(packages) > 100 or any(not APT_NAME.fullmatch(name) for name in packages):
        raise ValueError("apt-packages.txt contains an invalid package name or too many packages")
    return packages


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True, timeout=600)


def main() -> None:
    shutil.copytree(SOURCE, BUILD)
    apt_file = BUILD / "apt-packages.txt"
    if apt_file.is_file():
        packages = apt_packages(apt_file)
        if packages:
            run("apt-get", "update")
            run("apt-get", "install", "-y", "--no-install-recommends", *packages)
            shutil.rmtree("/var/lib/apt/lists", ignore_errors=True)
    requirements = BUILD / "requirements.txt"
    if requirements.is_file():
        run("python", "-m", "pip", "install", "--no-cache-dir", "-r", str(requirements), cwd=BUILD)
    package_json = BUILD / "package.json"
    if package_json.is_file():
        if not (BUILD / "package-lock.json").is_file():
            raise ValueError("A Skill with package.json must include package-lock.json")
        run("npm", "ci", "--omit=dev", "--prefix", str(BUILD))
        target = Path("/opt/movo-skill-node-modules")
        if (BUILD / "node_modules").is_dir():
            shutil.move(str(BUILD / "node_modules"), target)
    shutil.rmtree(BUILD)


if __name__ == "__main__":
    main()
