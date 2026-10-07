"""Shared strict demo markers for both sites."""
from pathlib import Path
import re
from .errors import BuildError

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIRS = {site: ROOT / "content" / site / "demos" for site in ("bible-garden", "lampada")}
MARKER_RE = re.compile(r"^<!-- demo: ([a-z0-9]+(?:-[a-z0-9]+)*) -->$")
INTENT_RE = re.compile(r"<!--\s*(?:demo|dmeo|demmo)\b", re.IGNORECASE)

def placeholder_for(demo_id: str) -> str:
    return f'<div data-demo-placeholder="{demo_id}"></div>'


def annotate_demo_marker(
    body: str, source: Path, site: str, body_start_line: int = 1, demos_dir: Path | None = None
) -> tuple[str, str | None]:
    directory = demos_dir if demos_dir is not None else DEMO_DIRS.get(site)

    lines = body.splitlines()
    fenced = fenced_flags(lines)
    found_id: str | None = None
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT_RE.search(line):
            continue
        match = MARKER_RE.fullmatch(line)
        if not match:
            raise BuildError(f"{source}:{body_start_line + index}: expected <!-- demo: <id> -->")
        demo_id = match.group(1)
        if directory is None or not (directory / f"{demo_id}.json").is_file():
            raise BuildError(f"{source}:{body_start_line + index}: unknown demo {demo_id!r} for {site}")
        if found_id is not None:
            raise BuildError(f"{source}:{body_start_line + index}: duplicate demo marker")
        lines[index] = placeholder_for(demo_id)
        found_id = demo_id
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), found_id


FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def fenced_flags(lines: list[str]) -> list[bool]:
    """Whether each line sits inside a fenced code block, fence lines included (CommonMark rules).

    An opening fence is 3+ backticks or tildes indented by at most 3 spaces (a backtick fence
    has no backtick in its info string); it closes with the same character, at least as long,
    followed only by spaces.
    """
    flags: list[bool] = []
    fence: str | None = None
    for line in lines:
        match = FENCE_RE.match(line)
        if fence is None:
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                fence = match.group(1)
                flags.append(True)
            else:
                flags.append(False)
        else:
            flags.append(True)
            marker = match.group(1) if match else ""
            if match and marker[0] == fence[0] and len(marker) >= len(fence) and not match.group(2).strip():
                fence = None
    return flags


def unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")
