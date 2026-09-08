#!/usr/bin/env python3
"""Generate the standalone repository's CI workflow from the profile repo's.

The project currently lives in a subdirectory, so GitHub runs
``.github/workflows/fiscalkit.yml`` at the profile repo root and never runs
``fiscalkit/.github/workflows/ci.yml``. That second file is the one the project
keeps when it is extracted, and the one the README's badge points at.

Because it never runs here, it silently went stale: it was written in the first
commit and still had two jobs while the workflow that actually runs had grown to
seven, including every job that has caught a real bug -- the MCP-absent build,
the ``mcp<2`` pin, the differential suite, the Action dogfood, and the packaging
checks. Extracting the project would have swapped a CI that proves things for one
that does not, under a badge claiming otherwise.

This script derives one from the other so they cannot diverge, and
``test_standalone_ci_matches_the_workflow_that_runs`` fails if they have.

Run it after editing the root workflow::

    python tools/sync_ci.py          # rewrite the standalone workflow
    python tools/sync_ci.py --check  # exit 1 if it is out of date
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADER_FROM = """name: fiscalkit

# GitHub only runs workflows found in .github/workflows at the repository root,
# so fiscalkit/.github/workflows/ci.yml never fires while the project lives in a
# subdirectory. That copy is the one the project keeps once it is extracted into
# its own repository; this one verifies it in the meantime.
#
# Path-filtered so ordinary profile README edits do not trigger a Python matrix.

on:
  push:
    branches: [main]
    paths:
      - "fiscalkit/**"
      - ".github/workflows/fiscalkit.yml"
  pull_request:
    paths:
      - "fiscalkit/**"
      - ".github/workflows/fiscalkit.yml"

defaults:
  run:
    working-directory: fiscalkit

jobs:"""

HEADER_TO = """name: CI

# This is the workflow the project runs once it lives in its own repository, and
# the one the README's badge points at. It is generated from the profile repo's
# .github/workflows/fiscalkit.yml by tools/sync_ci.py, so the two cannot drift:
# every job that has ever caught a bug here is a job that runs on day one there.
#
# No path filter and no working-directory: in a standalone repository every
# change is this project's, and the repository root is the package root.

on:
  push:
    branches: [main]
  pull_request:

jobs:"""

#: The dogfood job overrides the workflow-level working-directory. With no such
#: default in the standalone repo the override is meaningless, so the block and
#: the comment explaining it are dropped. Matched by pattern rather than copied
#: as a literal, so rewording that comment upstream does not silently stop the
#: removal from happening.
WORKING_DIR_OVERRIDE = re.compile(
    r"[ \t]*#[^\n]*\n(?:[ \t]*#[^\n]*\n)*"
    r"[ \t]*defaults:\n[ \t]*run:\n[ \t]*working-directory: \.\n"
)

#: Paths are relative to the profile repo root on the left, and to the package
#: root on the right, because in the standalone repo they are the same directory.
REWRITES = (
    ("uses: ./fiscalkit", "uses: ./"),
    ("version: ./fiscalkit", "version: ./"),
    ("pip install ./fiscalkit", "pip install ."),
    ("fiscalkit/tests/fixtures/legacy_project", "tests/fixtures/legacy_project"),
    ("fiscalkit/src/fiscalkit/documents", "src/fiscalkit/documents"),
)


def render(root_workflow: str) -> str:
    """Return the standalone workflow derived from *root_workflow*."""
    if HEADER_FROM not in root_workflow:
        raise SystemExit(
            "the root workflow's header no longer matches what this script expects; "
            "update HEADER_FROM/HEADER_TO in tools/sync_ci.py before syncing"
        )
    out = root_workflow.replace(HEADER_FROM, HEADER_TO, 1)
    out = WORKING_DIR_OVERRIDE.sub("", out, count=1)
    for old, new in REWRITES:
        out = out.replace(old, new)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if out of date")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent.parent
    source = here.parent / ".github" / "workflows" / "fiscalkit.yml"
    target = here / ".github" / "workflows" / "ci.yml"

    if not source.is_file():
        print(f"no profile-repo workflow at {source}; nothing to sync", file=sys.stderr)
        return 0

    expected = render(source.read_text(encoding="utf-8"))
    if args.check:
        if target.read_text(encoding="utf-8") != expected:
            print(f"{target} is out of date; run: python tools/sync_ci.py", file=sys.stderr)
            return 1
        print(f"{target} is up to date")
        return 0

    target.write_text(expected, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
