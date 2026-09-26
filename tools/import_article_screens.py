"""Import the accepted screenshot archive as reproducible article WebP assets."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sitegen.content import load_site  # noqa: E402
from sitegen.screens import ASSET_DIR, SOURCE_SIZES, VARIANTS, load_catalog, webp_dimensions  # noqa: E402

ARCHIVE_SHA256 = "70a13a2da5727fe0671eb6a712a7448485f7ec9e3ede220ecc384fa547a2e9fb"
CWEBP_VERSION = "1.3.2"
SOURCE_PREFIX = "bible-garden-screens/"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def import_archive(archive: Path, site_config: Path) -> int:
    with archive.open("rb") as archive_file:
        digest = hashlib.file_digest(archive_file, "sha256").hexdigest()
    if digest != ARCHIVE_SHA256:
        raise ValueError(f"{archive}: SHA-256 differs from the accepted archive")
    try:
        version = subprocess.check_output(["cwebp", "-version"], text=True).splitlines()[0]
    except FileNotFoundError as error:
        raise RuntimeError(f"cwebp {CWEBP_VERSION} is required") from error
    if version != CWEBP_VERSION:
        raise RuntimeError(f"cwebp {CWEBP_VERSION} required, found {version}")

    if site_config.name != "site.yaml":
        raise ValueError(f"{site_config}: expected a site.yaml path")
    content_dir = site_config.resolve().parent
    site = load_site(content_dir, REPO_ROOT)
    source_root = REPO_ROOT / "static" / site.key
    catalog = load_catalog(content_dir / "screens.yaml", site.languages)
    expected = {
        f"{SOURCE_PREFIX}{screen.id}.{lang}.png": (screen, lang)
        for screen in catalog.values()
        for lang in screen.captions
    }
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory() as scratch:
        names = {name for name in source.namelist() if name.lower().endswith(".png")}
        if names != set(expected):
            missing, extra = sorted(set(expected) - names), sorted(names - set(expected))
            raise ValueError(f"{archive}: screenshot names differ: missing={missing}, extra={extra}")
        staged = Path(scratch)
        checksums: dict[Path, str] = {}
        for name, (screen, lang) in sorted(expected.items()):
            png = staged / f"{screen.id}.{lang}.png"
            with source.open(name) as input_file, png.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file)
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
    parser.add_argument("archive", type=Path, help="accepted screenshot ZIP archive")
    args = parser.parse_args()
    print(f"updated {import_archive(args.archive, args.site_config)} files")


if __name__ == "__main__":
    main()
