"""Shared strict demo markers for both sites."""
from pathlib import Path
import re
from .errors import BuildError

ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR = ROOT / "content/bible-garden/demos"
MARKER_RE = re.compile(r"^<!-- demo: ([a-z0-9]+(?:-[a-z0-9]+)*) -->$")
INTENT_RE = re.compile(r"<!--\s*(?:demo|dmeo|demmo)\b", re.IGNORECASE)

def placeholder_for(demo_id: str) -> str:
    return f'<div data-demo-placeholder="{demo_id}"></div>'


def annotate_demo_marker(
    body: str, source: Path, site: str, body_start_line: int = 1, demos_dir: Path = DEMOS_DIR
) -> tuple[str, str | None]:
    from .content import _fenced_flags

    directory = ROOT / "content/lampada/demos" if site == "lampada" and demos_dir == DEMOS_DIR else demos_dir

    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found_id: str | None = None
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT_RE.search(line):
            continue
        match = MARKER_RE.fullmatch(line)
        if not match:
            raise BuildError(f"{source}:{body_start_line + index}: expected <!-- demo: <id> -->")
        demo_id = match.group(1)
        if site not in {"bible-garden", "lampada"} or not (directory / f"{demo_id}.json").is_file():
            raise BuildError(f"{source}:{body_start_line + index}: unknown demo {demo_id!r} for {site}")
        if found_id is not None:
            raise BuildError(f"{source}:{body_start_line + index}: duplicate demo marker")
        lines[index] = placeholder_for(demo_id)
        found_id = demo_id
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), found_id
