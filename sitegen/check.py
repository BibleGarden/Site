"""Validation of the generated HTML: every JSON-LD block must be well-formed."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .build import REPO_ROOT
from .errors import BuildError

JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
SKIPPED_DIRS = {".git", "content", "templates", "sitegen", ".venv"}


def html_files() -> list[Path]:
    return sorted(
        path for path in REPO_ROOT.rglob("*.html") if not SKIPPED_DIRS & set(path.relative_to(REPO_ROOT).parts)
    )


def check_json_ld() -> int:
    blocks = 0
    for path in html_files():
        for match in JSON_LD_RE.finditer(path.read_text(encoding="utf-8")):
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError as error:
                raise BuildError(f"{path}: invalid JSON-LD: {error}") from error
            if not isinstance(data, dict) or "@type" not in data or "@context" not in data:
                raise BuildError(f"{path}: JSON-LD block must be an object with @context and @type")
            blocks += 1
    return blocks
