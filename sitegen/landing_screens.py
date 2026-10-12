"""Lampada landing screenshots: committed WebP files verified against the importer's checksums."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import BuildError
from .screens import webp_dimensions

# Carousel order; the importer reads iphone-6.9-<lang>-<NN>-<id>.png, NN being the 1-based position.
SCREENS = ("home", "topic", "question", "answer", "audio", "passage", "reflection", "history")
SOURCE_SIZE = (1320, 2868)
WIDTH = 600
HEIGHT = (SOURCE_SIZE[1] * WIDTH + SOURCE_SIZE[0] - 1) // SOURCE_SIZE[0]
ASSET_DIR = Path("assets/screens")
CHECKSUM_LINE_RE = re.compile(r"([0-9a-f]{64})  (assets/screens/[a-z]+\.[a-z]{2}\.webp)")


@dataclass(frozen=True)
class LandingScreen:
    id: str
    url: str
    width: int = WIDTH
    height: int = HEIGHT


def asset_path(screen_id: str, lang: str) -> Path:
    return ASSET_DIR / f"{screen_id}.{lang}.webp"


def load_landing_screens(static_dir: Path, checksum_file: Path, languages: tuple[str, ...]) -> dict[str, dict[str, LandingScreen]]:
    """Return {lang: {id: screen}} in carousel order after checking every committed file."""
    expected = {asset_path(screen_id, lang) for screen_id in SCREENS for lang in languages}
    if not checksum_file.is_file():
        raise BuildError(f"{checksum_file}: missing landing screenshot checksums")
    checksums: dict[Path, str] = {}
    for line_number, line in enumerate(checksum_file.read_text(encoding="utf-8").splitlines(), start=1):
        match = CHECKSUM_LINE_RE.fullmatch(line)
        if not match or Path(match.group(2)) in checksums:
            raise BuildError(f"{checksum_file}:{line_number}: invalid or duplicate checksum entry")
        checksums[Path(match.group(2))] = match.group(1)
    if set(checksums) != expected:
        raise BuildError(f"{checksum_file}: checksum paths differ: missing={sorted(map(str, expected - set(checksums)))}, extra={sorted(map(str, set(checksums) - expected))}")
    actual = {path.relative_to(static_dir) for path in (static_dir / ASSET_DIR).rglob("*") if path.is_file()}
    if actual != expected:
        raise BuildError(f"{static_dir / ASSET_DIR}: landing screenshots differ: missing={sorted(map(str, expected - actual))}, extra={sorted(map(str, actual - expected))}")
    for relative in sorted(expected):
        path = static_dir / relative
        if webp_dimensions(path) != (WIDTH, HEIGHT):
            raise BuildError(f"{path}: landing screenshot dimensions {webp_dimensions(path)}, expected {(WIDTH, HEIGHT)}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksums[relative]:
            raise BuildError(f"{path}: landing screenshot checksum differs from the accepted import")
    return {lang: {screen_id: LandingScreen(screen_id, "/" + asset_path(screen_id, lang).as_posix()) for screen_id in SCREENS} for lang in languages}
