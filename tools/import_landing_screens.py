"""Import Lampada landing screenshots from a pinned Lampada-Mobile commit as reproducible WebP."""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sitegen.content import load_site  # noqa: E402
from sitegen.landing_screens import ASSET_DIR, HEIGHT, SCREENS, SOURCE_SIZE, WIDTH, asset_path  # noqa: E402
from sitegen.screens import require_cwebp, webp_dimensions  # noqa: E402

SOURCE_COMMIT = "fdceb3987d0323e161f2d944cd78ef04d33190ad"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CONTENT_DIR = REPO_ROOT / "content" / "lampada"
STATIC_DIR = REPO_ROOT / "static" / "lampada"
CHECKSUM_FILE = CONTENT_DIR / "landing-screens.sha256"


def import_screens(mobile_repo: Path) -> int:
    require_cwebp()
    languages = load_site(CONTENT_DIR, REPO_ROOT).languages
    expected = {asset_path(screen_id, lang) for screen_id in SCREENS for lang in languages}
    data: dict[Path, bytes] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for number, screen_id in enumerate(SCREENS, start=1):
            for lang in languages:
                source = f"store/screenshots/iphone-6.9-{lang}-{number:02d}-{screen_id}.png"
                png_bytes = subprocess.run(
                    ["git", "-C", str(mobile_repo), "show", f"{SOURCE_COMMIT}:{source}"], capture_output=True, check=True
                ).stdout
                if png_bytes[:8] != PNG_SIGNATURE or png_bytes[12:16] != b"IHDR":
                    raise ValueError(f"{source}: invalid PNG header")
                if struct.unpack(">II", png_bytes[16:24]) != SOURCE_SIZE:
                    raise ValueError(f"{source}: PNG dimensions differ from {SOURCE_SIZE}")
                png = Path(scratch) / f"{screen_id}.{lang}.png"
                png.write_bytes(png_bytes)
                target = Path(scratch) / f"{screen_id}.{lang}.webp"
                subprocess.run(
                    ["cwebp", "-quiet", "-q", "88", "-resize", str(WIDTH), "0", "-metadata", "none", str(png), "-o", str(target)],
                    check=True,
                )
                if webp_dimensions(target) != (WIDTH, HEIGHT):
                    raise ValueError(f"{source}: WebP dimensions {webp_dimensions(target)} differ from {(WIDTH, HEIGHT)}")
                data[asset_path(screen_id, lang)] = target.read_bytes()

    existing = {path.relative_to(STATIC_DIR) for path in (STATIC_DIR / ASSET_DIR).rglob("*") if path.is_file()} if (STATIC_DIR / ASSET_DIR).exists() else set()
    if stale := existing - expected:
        raise ValueError(f"stale landing screenshots: {', '.join(map(str, sorted(stale)))}")
    changed = 0
    for relative, payload in sorted(data.items()):
        target = STATIC_DIR / relative
        if target.exists() and target.read_bytes() == payload:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        changed += 1
    checksum_text = "".join(f"{hashlib.sha256(payload).hexdigest()}  {relative.as_posix()}\n" for relative, payload in sorted(data.items()))
    if not CHECKSUM_FILE.exists() or CHECKSUM_FILE.read_text(encoding="utf-8") != checksum_text:
        CHECKSUM_FILE.write_text(checksum_text, encoding="utf-8")
        changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mobile_repo", type=Path, help=f"Lampada-Mobile clone containing commit {SOURCE_COMMIT}")
    args = parser.parse_args()
    print(f"updated {import_screens(args.mobile_repo)} files")


if __name__ == "__main__":
    main()
