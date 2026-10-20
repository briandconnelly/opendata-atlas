#!/usr/bin/env python
"""Rehearse the release cut on a temp copy, using release.yml's own programs.

``release.yml`` checks that pyproject, manifest.json, the first ``## [X.Y.Z]`` CHANGELOG
heading and the tag agree, then extracts that CHANGELOG section as the release notes. This
script pulls both programs out of the workflow text (it keeps no copy of them), copies the
three files they read to a work directory, cuts the copy, and runs them there.

Usage:
    uv run python scripts/rehearse_release.py [--version V] [--date YYYY-MM-DD]
    uv run python scripts/rehearse_release.py --apply [--version V] [--date YYYY-MM-DD]

Without ``--apply`` nothing in the repository changes. ``--apply`` rehearses first, then writes
the cut to ``CHANGELOG.md``; commit it, then tag.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
UNRELEASED = "## [Unreleased]"
_CHECK = re.compile(r"<<'PY'\n(.*?)\n\s*PY\n", re.S)
_AWK = re.compile(r"awk -v v=\"\$version\" '\n(.*?)\n\s*' CHANGELOG\.md", re.S)


def cut_changelog(text: str, version: str, day: str) -> str:
    """Rename the first ``## [Unreleased]`` heading to ``## [<version>] - <day>``."""
    if UNRELEASED not in text:
        raise ValueError(f"CHANGELOG has no {UNRELEASED} heading to cut")
    return text.replace(UNRELEASED, f"## [{version}] - {day}", 1)


def version_check_program(workflow: str) -> str:
    """The version-agreement step's Python program, verbatim and dedented."""
    matches = _CHECK.findall(workflow)
    if len(matches) != 1:
        raise ValueError(
            f"release.yml has {len(matches)} <<'PY' heredocs; "
            "expected exactly one, the version-check step"
        )
    return textwrap.dedent(matches[0]) + "\n"


def notes_awk_program(workflow: str) -> str:
    """The notes-extraction step's awk program, verbatim."""
    match = _AWK.search(workflow)
    if not match:
        raise ValueError("release.yml no longer extracts notes with this awk call")
    return match.group(1)


@dataclass
class Rehearsal:
    ok: bool
    check_output: str
    notes: str


def rehearse(root: Path, version: str, day: str, work: Path, tag: str | None = None) -> Rehearsal:
    """Cut a copy of ``root``'s release files in ``work`` and run the workflow's steps on it.

    A CHANGELOG that is already cut (no ``## [Unreleased]``) is checked as it stands. ``tag`` is
    a real git tag to compare, as the workflow does; without one the check skips the tag.
    """
    workflow = (root / ".github" / "workflows" / "release.yml").read_text()
    for name in ("pyproject.toml", "manifest.json", "CHANGELOG.md"):
        shutil.copy2(root / name, work / name)
    changelog = work / "CHANGELOG.md"
    text = changelog.read_text()
    if UNRELEASED in text:
        changelog.write_text(cut_changelog(text, version, day))
    else:
        released = re.search(r"^## \[(\d+\.\d+\.\d+[^\]]*)\]", text, re.M)
        if not released or released.group(1) != version:
            found = released.group(1) if released else None
            return Rehearsal(False, f"CHANGELOG is already cut as {found!r}, not {version!r}", "")
    # Not `uv run`: that would try to sync the copied pyproject.toml.
    check = subprocess.run(
        [sys.executable, "-", tag or ""],
        input=version_check_program(workflow),
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    notes = subprocess.run(
        ["awk", "-v", f"v={version}", notes_awk_program(workflow), "CHANGELOG.md"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return Rehearsal(
        ok=check.returncode == 0 and bool(notes.strip()),
        check_output=(check.stdout + check.stderr).strip(),
        notes=notes,
    )


def head_tag() -> str | None:
    """The ``v*`` tag on HEAD, if any."""
    out = subprocess.run(
        ["git", "tag", "--points-at", "HEAD", "--list", "v*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return out[0] if out else None


def tag_exists(name: str) -> bool:
    """Whether the tag ``name`` exists anywhere in the repository."""
    out = subprocess.run(
        ["git", "tag", "--list", name],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return bool(out.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", help="default: pyproject's version")
    parser.add_argument(
        "--date", default=date.today().isoformat(), help="YYYY-MM-DD, default today"
    )
    parser.add_argument(
        "--apply", action="store_true", help="after a passing rehearsal, cut CHANGELOG.md"
    )
    args = parser.parse_args(argv)
    try:
        version = (
            args.version
            or tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]["version"]
        )
        tag = head_tag()
        # A tagged HEAD may still be verified read-only, but never cut again.
        if (tag is None or args.apply) and tag_exists(f"v{version}"):
            print(
                f"FAIL: v{version} is already tagged; bump the version in pyproject.toml, "
                "then run scripts/gen_manifest.py"
            )
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            result = rehearse(REPO_ROOT, version, args.date, Path(tmp), tag)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}")
        return 1
    if not result.ok:
        print(f"FAIL: {result.check_output or 'the release notes are empty'}")
        return 1
    print(result.check_output)
    print(f"tag: {tag}" if tag else f"tag: none yet (would be v{version})")
    print(f"release notes: {len(result.notes.splitlines())} lines")
    if args.apply:
        path = REPO_ROOT / "CHANGELOG.md"
        try:
            path.write_text(cut_changelog(path.read_text(), version, args.date))
        except (ValueError, OSError) as error:
            print(f"FAIL: {error}")
            return 1
        print(f"cut {path.name} as {version} - {args.date}; commit it, then tag v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
