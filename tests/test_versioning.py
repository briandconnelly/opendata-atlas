"""A renamed server is a new server [9.rename]: its own version line, and the fork stated.

`release.yml` checks the first `## [X.Y.Z]` heading against pyproject and publishes that
section as the release notes, so seattle-open-data's history must not use that form.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from fastmcp import Client

from opendata_atlas import __version__
from opendata_atlas.core.reference import CAPABILITIES
from opendata_atlas.mcp.server import build_server

ROOT = Path(__file__).resolve().parent.parent
#: release.yml's "latest released section" pattern.
RELEASED = re.compile(r"^## \[(\d+\.\d+\.\d+[^\]]*)\]", re.M)
HISTORY = "## [seattle-open-data history]"
#: The first release, whose section states the fork.
FIRST = "0.1.0"
DAY = "2026-10-19"
#: Set in the nested pytest run of `test_suite_passes_after_apply`, so it does not recurse.
NESTED = "ATLAS_VERSIONING_NESTED"
#: release.yml runs these steps with awk on ubuntu-latest; Windows awk (and its CRLF temp files)
#: is not what they run on, so the tests that run them skip there.
needs_awk = pytest.mark.skipif(
    shutil.which("awk") is None or sys.platform == "win32",
    reason="needs POSIX awk, as release.yml runs on ubuntu-latest",
)


@pytest.fixture(scope="session")
def rehearsal():
    """scripts/rehearse_release.py, loaded here so a script error fails only the tests using it."""
    path = ROOT / "scripts" / "rehearse_release.py"
    spec = importlib.util.spec_from_file_location("rehearse_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass resolves its module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def workflow() -> str:
    return (ROOT / ".github" / "workflows" / "release.yml").read_text()


@pytest.fixture(scope="session")
def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def changelog_states(text: str, rehearsal, version: str) -> dict[str, str]:
    """The CHANGELOG before and after `version`'s cut, whichever state `text` is in.

    An uncut tree (`## [Unreleased]` and no `version` section) is cut in memory. A cut tree
    (`## [<version>] - date`) has that heading renamed back to build the uncut state. A tree
    reopened after the release (`## [Unreleased]` above `## [<version>] - date`, checklist
    step 12) is treated as the cut tree without the reopened section.
    """
    match = RELEASED.search(text)
    unreleased = text.find("## [Unreleased]")
    if match and match.group(1) == version and 0 <= unreleased < match.start():
        text = text[:unreleased] + text[match.start() :]
        match = RELEASED.search(text)
    elif unreleased >= 0:
        return {"uncut": text, "cut": rehearsal.cut_changelog(text, version, DAY)}
    assert match and match.group(1) == version, "a cut CHANGELOG's first section is pyproject's"
    heading = text[match.start() : text.index("\n", match.start())]
    return {"uncut": text.replace(heading, "## [Unreleased]", 1), "cut": text}


@pytest.fixture(scope="session")
def states(rehearsal, version) -> dict[str, str]:
    """The CHANGELOG before and after the cut, whichever the tree holds now."""
    return changelog_states((ROOT / "CHANGELOG.md").read_text(), rehearsal, version)


def release_section(text: str) -> str:
    """The first `## [X.Y.Z]` section when one exists, else `## [Unreleased]`."""
    match = RELEASED.search(text)
    heading = match.group(0) if match else "## [Unreleased]"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def first_release_section(text: str) -> str:
    """The `## [0.1.0]` section, or `## [Unreleased]` before 0.1.0 was cut."""
    heading = f"## [{FIRST}]" if f"## [{FIRST}]" in text else "## [Unreleased]"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


async def test_served_version_is_the_package_version():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    async with Client(build_server(), mode="legacy") as client:
        assert client.initialize_result is not None
        assert client.initialize_result.server_info.version == pyproject
    assert __version__ == pyproject
    assert CAPABILITIES.splitlines()[0] == f"# opendata-atlas {pyproject}"


@pytest.mark.parametrize("state", ["uncut", "cut"])
def test_changelog_states_the_fork(states, state):
    section = first_release_section(states[state])
    assert "new server" in section
    assert "forked from seattle-open-data 0.2.0 at 26c6628" in section
    assert "`seattle_data_*` to `atlas_*`" in section


@pytest.mark.parametrize("state", ["uncut", "cut"])
def test_parent_history_cannot_be_released_as_this_server(states, state):
    text = states[state]
    assert HISTORY in text
    history = text.split(HISTORY, 1)[1]
    assert not RELEASED.search(history), "a parent section would pass release.yml's check"
    assert not RELEASED.match(HISTORY), "the history heading must not read as a version"


@needs_awk
def test_release_notes_stop_before_parent_history(rehearsal, workflow, version, states, tmp_path):
    """The cut section as the release notes must not publish seattle-open-data's entries."""
    (tmp_path / "CHANGELOG.md").write_text(states["cut"])
    notes = subprocess.run(
        ["awk", "-v", f"v={version}", rehearsal.notes_awk_program(workflow), "CHANGELOG.md"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert notes.strip() == release_section(states["cut"]).split("\n", 1)[1].strip()
    history = states["cut"].split(HISTORY, 1)[1]
    assert "seattle-open-data 0.2.0 - 2026-10-16" in history
    for leaked in (
        "seattle-open-data history",
        "seattle-open-data 0.2.0 - ",
        "seattle_data_search",
    ):
        assert leaked not in notes


def _stage(tmp_path: Path, changelog: str) -> None:
    for name in ("pyproject.toml", "manifest.json"):
        shutil.copy2(ROOT / name, tmp_path / name)
    (tmp_path / "CHANGELOG.md").write_text(changelog)


def test_uncut_changelog_fails_the_workflow_check(rehearsal, workflow, version, states, tmp_path):
    """Known positive for the extracted check: it must be able to fail (releasing.md Context)."""
    _stage(tmp_path, states["uncut"])
    result = subprocess.run(
        [sys.executable, "-", f"v{version}"],
        input=rehearsal.version_check_program(workflow),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "latest CHANGELOG version" in result.stdout
    assert f"!= pyproject version {version!r}" in result.stdout


@needs_awk
def test_rehearsal_passes_on_a_cut_copy(rehearsal, version, states, tmp_path):
    before = (ROOT / "CHANGELOG.md").read_bytes()
    result = rehearsal.rehearse(ROOT, version, DAY, tmp_path)
    assert result.ok, result.check_output
    assert release_section(states["cut"]).split("\n", 1)[1].strip() in result.notes
    assert "seattle-open-data history" not in result.notes
    assert (ROOT / "CHANGELOG.md").read_bytes() == before


@needs_awk
def test_rehearsal_rejects_a_mismatched_version(rehearsal, version, tmp_path):
    major, minor, patch = version.split(".")
    wrong = f"{major}.{minor}.{int(patch) + 1}"
    result = rehearsal.rehearse(ROOT, wrong, DAY, tmp_path)
    assert not result.ok
    assert wrong in result.check_output


@needs_awk
def test_rehearsal_rejects_a_mismatched_tag(rehearsal, version, tmp_path):
    result = rehearsal.rehearse(ROOT, version, DAY, tmp_path, tag="v9.9.9")
    assert not result.ok
    assert "git tag version '9.9.9'" in result.check_output


def test_cut_requires_an_unreleased_heading(rehearsal, version, states):
    with pytest.raises(ValueError, match="no ## \\[Unreleased\\]"):
        rehearsal.cut_changelog(states["cut"], version, DAY)


def test_readme_status_matches_capability_tier():
    readme = (ROOT / "README.md").read_text()
    status = re.search(r"\*\*Status: (\w+)\.\*\*", readme)
    stability = re.search(r"- Stability: (\w+)", CAPABILITIES)
    assert status and stability
    assert status.group(1) == stability.group(1)


def test_rehearsal_names_a_second_check_heredoc(rehearsal, workflow):
    doubled = workflow + "\n          python - <<'PY'\n          print(1)\n          PY\n"
    with pytest.raises(ValueError, match="version-check"):
        rehearsal.version_check_program(doubled)


def test_cli_fails_in_one_line_on_a_missing_workflow(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / "rehearse_release.py", tmp_path / "scripts")
    _stage(tmp_path, (ROOT / "CHANGELOG.md").read_text())
    result = subprocess.run(
        [sys.executable, str(tmp_path / "scripts" / "rehearse_release.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert result.stdout.startswith("FAIL:")
    assert "Traceback" not in result.stderr


def _tagged_tree(tmp_path: Path, version: str, *, tag_at_head: bool) -> None:
    """A minimal git tree whose release commit carries ``v<version>``, maybe with one after it."""
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / "rehearse_release.py", tmp_path / "scripts")
    _stage(tmp_path, (ROOT / "CHANGELOG.md").read_text())
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    git += ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]
    steps = [["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "release"]]
    steps.append(["tag", f"v{version}"])
    if not tag_at_head:
        steps.append(["commit", "-q", "--allow-empty", "-m", "after the release"])
    for args in steps:
        subprocess.run([*git, *args], cwd=tmp_path, check=True, capture_output=True)


def _run_rehearsal(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "scripts" / "rehearse_release.py"
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git for the tag")
@pytest.mark.parametrize(
    ("tag_at_head", "args"),
    [(False, ()), (False, ("--apply",)), (True, ("--apply",))],
    ids=["tag-behind-head", "tag-behind-head-apply", "tag-at-head-apply"],
)
def test_cli_fails_when_the_version_is_already_tagged(version, tmp_path, tag_at_head, args):
    """A released version must be bumped before the next cut, wherever its tag is (releasing.md)."""
    _tagged_tree(tmp_path, version, tag_at_head=tag_at_head)
    result = _run_rehearsal(tmp_path, *args)
    assert result.returncode == 1
    assert result.stdout.startswith(f"FAIL: v{version} is already tagged")


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git for the tag")
def test_cli_still_verifies_a_tagged_head_read_only(version, tmp_path):
    """Without --apply, a tagged HEAD is checked as the workflow would, not refused as tagged."""
    _tagged_tree(tmp_path, version, tag_at_head=True)
    result = _run_rehearsal(tmp_path)
    assert "already tagged" not in result.stdout


def _copy_tree(dest: Path) -> None:
    skip = shutil.ignore_patterns(
        ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"
    )
    shutil.copytree(ROOT, dest, ignore=skip, symlinks=True)


@needs_awk
def test_apply_cuts_only_the_copy_it_runs_from(rehearsal, version, states, tmp_path):
    """`--apply` writes next to its own script, so a copied tree is cut and the repo is not."""
    _copy_tree(tmp_path / "tree")
    tree = tmp_path / "tree"
    (tree / "CHANGELOG.md").write_text(states["uncut"])
    before = (ROOT / "CHANGELOG.md").read_bytes()
    result = subprocess.run(
        [sys.executable, str(tree / "scripts" / "rehearse_release.py"), "--apply", "--date", DAY],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tree / "CHANGELOG.md").read_text() == rehearsal.cut_changelog(
        states["uncut"], version, DAY
    )
    assert (ROOT / "CHANGELOG.md").read_bytes() == before


@needs_awk
@pytest.mark.skipif(shutil.which("uv") is None, reason="runs the suite with uv, as CI does")
@pytest.mark.skipif(bool(os.environ.get(NESTED)), reason="the nested run does not recurse")
def test_suite_passes_after_apply(states, tmp_path):
    """The workflow tests the tagged, cut commit: this file must pass on it, not only before."""
    tree = tmp_path / "tree"
    _copy_tree(tree)
    (tree / "CHANGELOG.md").write_text(states["uncut"])
    cut = subprocess.run(
        [sys.executable, str(tree / "scripts" / "rehearse_release.py"), "--apply", "--date", DAY],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cut.returncode == 0, cut.stdout + cut.stderr
    assert "## [Unreleased]" not in (tree / "CHANGELOG.md").read_text()
    env = {**os.environ, NESTED: "1"}
    env.pop("VIRTUAL_ENV", None)
    run = subprocess.run(
        ["uv", "run", "pytest", "-q", "tests/test_versioning.py"],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]


REOPENED = "## [Unreleased]\n\n### Changed\n\n- A change after the release.\n\n"


def _reopen(cut: str) -> str:
    """`cut` with `## [Unreleased]` re-added above its first released heading (step 12)."""
    first = RELEASED.search(cut)
    assert first
    return cut[: first.start()] + REOPENED + cut[first.start() :]


def test_states_rebuild_the_release_from_a_reopened_changelog(rehearsal, version, states):
    """After the release, both states are the release's, with the reopened section left out."""
    rebuilt = changelog_states(_reopen(states["cut"]), rehearsal, version)
    assert rebuilt == states
    assert "A change after the release." not in rebuilt["uncut"] + rebuilt["cut"]


@needs_awk
@pytest.mark.skipif(shutil.which("uv") is None, reason="runs the suite with uv, as CI does")
@pytest.mark.skipif(bool(os.environ.get(NESTED)), reason="the nested run does not recurse")
def test_suite_passes_after_reopening(states, tmp_path):
    """The first commit after the release reopens `## [Unreleased]`: this file must pass on it."""
    tree = tmp_path / "tree"
    _copy_tree(tree)
    (tree / "CHANGELOG.md").write_text(_reopen(states["cut"]))
    env = {**os.environ, NESTED: "1"}
    env.pop("VIRTUAL_ENV", None)
    run = subprocess.run(
        ["uv", "run", "pytest", "-q", "tests/test_versioning.py"],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
