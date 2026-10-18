"""Import accepted article screenshots as reproducible WebP assets.

Bible Garden reads its pinned ZIP archive; Lampada reads PNGs from a pinned
Lampada-Mobile commit (the store screenshots behind its landing page).
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sitegen.content import load_site  # noqa: E402
from sitegen.landing_screens import SCREENS as LAMPADA_STORE_SCREENS  # noqa: E402
from sitegen.screens import ASSET_DIR, SOURCE_SIZES, VARIANTS, Screen, load_catalog, require_cwebp, webp_dimensions  # noqa: E402

ARCHIVE_SHA256 = "eabbb4eb5b3bd65fb1c0bba9adc5a9cfab894f39cf3ca8e353b098cf2a322154"
SOURCE_PREFIX = "bible-garden-screens/"
# Same pinned commit as tools/import_landing_screens.py: article and landing frames match.
LAMPADA_MOBILE_COMMIT = "fdceb3987d0323e161f2d944cd78ef04d33190ad"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def load_catalog_for(site_config: Path):
    if site_config.name != "site.yaml":
        raise ValueError(f"{site_config}: expected a site.yaml path")
    content_dir = site_config.resolve().parent
    site = load_site(content_dir, REPO_ROOT)
    return content_dir, site, load_catalog(content_dir / "screens.yaml", site.languages)


def import_archive(archive: Path, site_config: Path) -> int:
    with archive.open("rb") as archive_file:
        digest = hashlib.file_digest(archive_file, "sha256").hexdigest()
    if digest != ARCHIVE_SHA256:
        raise ValueError(f"{archive}: SHA-256 differs from the accepted archive")
    require_cwebp()
    content_dir, site, catalog = load_catalog_for(site_config)
    expected = {
        f"{SOURCE_PREFIX}{screen.id}.{lang}.png": (screen, lang)
        for screen in catalog.values()
        for lang in screen.captions
    }
    with zipfile.ZipFile(archive) as source:
        names = {name for name in source.namelist() if name.lower().endswith(".png")}
        if names != set(expected):
            missing, extra = sorted(set(expected) - names), sorted(names - set(expected))
            raise ValueError(f"{archive}: screenshot names differ: missing={missing}, extra={extra}")
        pngs = {(screen.id, lang): (name, source.read(name)) for name, (screen, lang) in expected.items()}
    return write_variants(content_dir, site.key, catalog, pngs)


def import_lampada_mobile(mobile_repo: Path, site_config: Path) -> int:
    """Lampada article screens reuse store screenshots: catalog id = landing screen id."""
    require_cwebp()
    content_dir, site, catalog = load_catalog_for(site_config)
    if site.key != "lampada":
        raise ValueError(f"{site_config}: Lampada-Mobile screenshots belong to the lampada site")
    pngs = {}
    for screen in catalog.values():
        if screen.id not in LAMPADA_STORE_SCREENS:
            raise ValueError(f"{screen.id}: not a Lampada store screenshot ({', '.join(LAMPADA_STORE_SCREENS)})")
        number = LAMPADA_STORE_SCREENS.index(screen.id) + 1
        for lang in screen.captions:
            name = f"store/screenshots/iphone-6.9-{lang}-{number:02d}-{screen.id}.png"
            data = subprocess.run(
                ["git", "-C", str(mobile_repo), "show", f"{LAMPADA_MOBILE_COMMIT}:{name}"], capture_output=True, check=True
            ).stdout
            pngs[(screen.id, lang)] = (name, data)
    return write_variants(content_dir, site.key, catalog, pngs)


def write_variants(content_dir: Path, site_key: str, catalog: dict[str, Screen], pngs: dict[tuple[str, str], tuple[str, bytes]]) -> int:
    source_root = REPO_ROOT / "static" / site_key
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch)
        checksums: dict[Path, str] = {}
        for (screen_id, lang), (name, png_bytes) in sorted(pngs.items()):
            screen = catalog[screen_id]
            png = staged / f"{screen.id}.{lang}.png"
            png.write_bytes(png_bytes)
            with png.open("rb") as png_file:
                header = png_file.read(24)
            if header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
                raise ValueError(f"{name}: invalid PNG header")
            dimensions = struct.unpack(">II", header[16:24])
            if dimensions != SOURCE_SIZES[screen.kind]:
                raise ValueError(f"{name}: PNG dimensions {dimensions} differ from catalog kind {screen.kind}")
            for variant, width in VARIANTS.items():
                target = staged / screen.path(lang, variant)
                target.parent.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    ["cwebp", "-q", "88", "-resize", str(width), "0", "-metadata", "none", str(png), "-o", str(target)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode:
                    raise RuntimeError(f"{name} ({variant}): cwebp failed: {result.stderr.strip()}")
                actual_size = webp_dimensions(target)
                if actual_size != screen.dimensions(variant):
                    raise ValueError(f"{name} ({variant}): WebP dimensions {actual_size} differ from {screen.dimensions(variant)}")
                checksum = hashlib.sha256(target.read_bytes()).hexdigest()
                checksums[screen.path(lang, variant)] = checksum

        expected_webp = {
            screen.path(lang, variant)
            for screen in catalog.values()
            for lang in screen.captions
            for variant in VARIANTS
        }
        asset_dir = source_root / ASSET_DIR
        existing_webp = {path.relative_to(source_root) for path in asset_dir.rglob("*.webp")} if asset_dir.exists() else set()
        if extra := existing_webp - expected_webp:
            raise ValueError(f"stale screenshot files: {', '.join(map(str, sorted(extra)))}")
        changed = 0
        for relative in sorted(expected_webp):
            target = source_root / relative
            data = (staged / relative).read_bytes()
            if target.exists() and target.read_bytes() == data:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            changed += 1
        checksum_file = content_dir / "screens.sha256"
        checksum_text = "".join(f"{checksums[path]}  {path.as_posix()}\n" for path in sorted(checksums))
        if not checksum_file.exists() or checksum_file.read_text(encoding="utf-8") != checksum_text:
            checksum_file.write_text(checksum_text, encoding="utf-8")
            changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-config", type=Path, required=True, help="path to the site's content/<site>/site.yaml")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path, help="accepted Bible Garden screenshot ZIP archive")
    source.add_argument("--mobile-repo", type=Path, help=f"Lampada-Mobile clone containing commit {LAMPADA_MOBILE_COMMIT}")
    args = parser.parse_args()
    if args.archive:
        changed = import_archive(args.archive, args.site_config)
    else:
        changed = import_lampada_mobile(args.mobile_repo, args.site_config)
    print(f"updated {changed} files")


if __name__ == "__main__":
    main()
