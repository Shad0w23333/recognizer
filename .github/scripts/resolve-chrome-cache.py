"""Validate setup-chrome v1's macOS cache before its incorrect cache-hit path."""

import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import stat
import subprocess
import sys
from typing import Optional

VERSION = "131.0.6778.33"
APP = Path("Google Chrome for Testing.app")
BINARY = APP / "Contents/MacOS/Google Chrome for Testing"


class CacheError(ValueError):
    pass


def checked_path(path: Path, boundary: Path) -> Path:
    cursor = boundary
    for part in path.relative_to(boundary).parts:
        cursor /= part
        if cursor.is_symlink():
            raise CacheError("Chrome cache contains a symbolic link: " + str(cursor))
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(boundary)
    except (OSError, ValueError) as error:
        raise CacheError("Chrome cache is incomplete or escapes its directory: " + str(path)) from error
    return resolved


def resolve_cache(tool_cache: Path) -> Optional[Path]:
    if not tool_cache.is_absolute() or any(character in str(tool_cache) for character in "\r\n"):
        raise CacheError("RUNNER_TOOL_CACHE must be an absolute single-line path")
    boundary = tool_cache.resolve(strict=True)
    architecture = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}.get(platform.machine().lower())
    if architecture is None:
        raise CacheError("Unsupported macOS architecture")
    cache = boundary / "setup-chrome/chromium" / VERSION / architecture
    marker = cache.with_name(architecture + ".complete")

    def present(path: Path) -> bool:
        return path.exists() or path.is_symlink()

    if not present(cache) and not present(marker):
        return None  # A genuine cold miss still uses the original pinned installer.
    cache = checked_path(cache, boundary)
    marker = checked_path(marker, boundary)
    if not cache.is_dir() or not marker.is_file():
        raise CacheError("Chrome cache directory and complete marker are required")
    info = checked_path(cache / APP / "Contents/Info.plist", cache)
    try:
        metadata = plistlib.loads(info.read_bytes())
    except (OSError, ValueError) as error:
        raise CacheError("Chrome cache bundle metadata is invalid") from error
    if not isinstance(metadata, dict):
        raise CacheError("Chrome cache bundle metadata must be a dictionary")
    if metadata.get("CFBundleShortVersionString") != VERSION:
        raise CacheError("Cached Chrome bundle version does not match " + VERSION)
    executable = checked_path(cache / BINARY, cache)
    if not executable.is_file() or not executable.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) or not os.access(executable, os.X_OK):
        raise CacheError("Cached Chrome binary is not executable")
    try:
        result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise CacheError("Cached Chrome version probe failed") from error
    if result.stdout.strip() != "Google Chrome for Testing " + VERSION:
        raise CacheError("Actual cached Chrome version does not match " + VERSION)
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-cache", default=os.environ.get("RUNNER_TOOL_CACHE"))
    parser.add_argument("--output-file", default=os.environ.get("GITHUB_OUTPUT"))
    arguments = parser.parse_args()
    if platform.system() != "Darwin" or not arguments.tool_cache:
        parser.error("This resolver requires macOS and RUNNER_TOOL_CACHE")
    try:
        executable = resolve_cache(Path(arguments.tool_cache))
    except (CacheError, OSError) as error:
        print("Chrome cache validation failed: " + str(error), file=sys.stderr)
        return 1
    outputs = {"cache-hit": "true" if executable else "false"}
    if executable:
        outputs.update({"chrome-path": str(executable), "chrome-version": VERSION})
    if arguments.output_file:
        with Path(arguments.output_file).open("a", encoding="utf-8") as output:
            for key, value in outputs.items():
                output.write(key + "=" + value + "\n")
    print(json.dumps(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
