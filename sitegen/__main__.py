"""Command line entry point: python -m sitegen build | check."""

from __future__ import annotations

import sys

from .build import build_all
from .check import check_json_ld, html_files
from .errors import BuildError

USAGE = "usage: python -m sitegen build | check"


def main(argv: list[str]) -> int:
    if argv == ["build"]:
        written = build_all()
        print(f"wrote {len(written)} files")
        return 0
    if argv == ["check"]:
        blocks = check_json_ld()
        print(f"checked {blocks} JSON-LD blocks in {len(html_files())} HTML files")
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
