"""`atlas-profile <host> [--datasets N] [--out DIR] [--report PATH]`: write a draft pack.

A developer CLI, not an MCP tool (docs/design.md: The profiler). Exit codes: 0 written; 2 a
usage error (unknown host, `--out` exists or is missing); 3 the catalog identity did not
verify; 4 identity, the asset mix or the flagships failed upstream; 5 the rendered pack did not
load. For 3, 4 and 5 the report is written and no pack is.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import anyio

from opendata_atlas.core.http import SodaClient
from opendata_atlas.portals import freshness
from opendata_atlas.portals.loader import PackError, load_portal
from opendata_atlas.portals.registry import load_registry
from opendata_atlas.portals.validation import ValidationFile
from opendata_atlas.profiler.emit import pack_files
from opendata_atlas.profiler.profile import profile_portal

PORTALS_SUBDIR = Path("src/opendata_atlas/portals")
EXIT_USAGE = 2
EXIT_UNVERIFIED = 3
EXIT_UPSTREAM = 4
EXIT_INVALID_PACK = 5
REVIEW_HEADING = "Review these values before committing; drop any that identify a person"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atlas-profile",
        description="Profile a registered Socrata portal into draft pack files: observations "
        "only, with no interpretation, reliability or tier.",
    )
    p.add_argument("host", help="portal id, alias or public host, as in the registry")
    p.add_argument(
        "--datasets", type=int, default=10, help="flagship datasets to profile (default 10)"
    )
    p.add_argument(
        "--out",
        type=Path,
        help="draft pack directory; must not exist (default src/opendata_atlas/portals/<id> "
        "when that portals directory is under the working directory)",
    )
    p.add_argument("--report", type=Path, help="write the JSON report here (default stdout)")
    return p


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 (one return per exit code)
    parser = _parser()
    args = parser.parse_args(argv)
    if args.datasets < 1:
        parser.print_usage(sys.stderr)
        print("atlas-profile: --datasets must be at least 1", file=sys.stderr)
        return EXIT_USAGE
    registry = load_registry()
    entry = registry.by_alias(args.host) or next(
        (
            e
            for e in registry.entries.values()
            if e.identity.public_host.casefold() == args.host.casefold()
        ),
        None,
    )
    if entry is None:
        print(f"atlas-profile: {args.host!r} is not a registered portal", file=sys.stderr)
        return EXIT_USAGE
    out: Path | None = args.out
    if out is None:
        portals = Path.cwd() / PORTALS_SUBDIR
        if not portals.is_dir():
            print(f"atlas-profile: --out is required ({PORTALS_SUBDIR} not found)", file=sys.stderr)
            return EXIT_USAGE
        out = portals / entry.identity.id
    if out.exists():
        print(f"atlas-profile: {out} exists; choose a new --out", file=sys.stderr)
        return EXIT_USAGE

    async def run():
        client = SodaClient()
        try:
            return await profile_portal(
                client, entry, datasets=args.datasets, today=freshness.today()
            )
        finally:
            await client.aclose()

    report, claims = anyio.run(run)
    text = report.model_dump_json(indent=2) + "\n"
    if args.report is None:
        sys.stdout.write(text)
    else:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    if report.error is not None:
        print(f"atlas-profile: upstream failure, no pack written: {report.error}", file=sys.stderr)
        return EXIT_UPSTREAM
    if not report.identity_verified:
        print(f"atlas-profile: identity not verified: {report.identity_detail}", file=sys.stderr)
        return EXIT_UNVERIFIED
    files = pack_files(entry.identity, claims)
    error = _write_checked(files, out)
    if error is not None:
        print(f"atlas-profile: pack does not load, nothing written: {error}", file=sys.stderr)
        return EXIT_INVALID_PACK
    print(f"atlas-profile: wrote {len(claims)} claims to {out}", file=sys.stderr)
    if report.review_values:
        print(f"{REVIEW_HEADING}:", file=sys.stderr)
        for r in report.review_values:
            print(f"  {r.claim_id}: {json.dumps(r.value)}", file=sys.stderr)
    return 0


def _write_checked(files: dict[str, str], out: Path) -> str | None:
    """Write `files` to a temporary sibling of `out`, load it as a pack, then move it to `out`.

    Returns the loader's error, naming the file by its path under `out`, when it does not load;
    then nothing is left on disk.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        for name, body in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        try:
            load_portal(staging, validation=ValidationFile())
        except PackError as e:
            return str(e).replace(str(staging), str(out))
        staging.rename(out)
        return None
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    raise SystemExit(main())
