"""Shared article screenshots and their generated WebP variants."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from .errors import BuildError

ASSET_DIR = Path("img/article-screens")
VARIANTS = {"mobile": 360, "phone": 480, "zoom": 960}
SOURCE_SIZES = {"app": (1320, 2868), "system": (1284, 2778)}
SCREEN_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Screen:
    id: str
    kind: str
    captions: dict[str, str]

    def dimensions(self, variant: str) -> tuple[int, int]:
        width = VARIANTS[variant]
        source_width, source_height = SOURCE_SIZES[self.kind]
        return width, (source_height * width + source_width - 1) // source_width

    def path(self, lang: str, variant: str) -> Path:
        return ASSET_DIR / variant / f"{self.id}.{lang}.webp"

    def url(self, lang: str, variant: str) -> str:
        return "/" + self.path(lang, variant).as_posix()


@dataclass(frozen=True)
class ScreenRef:
    screen: Screen
    lang: str

    @property
    def caption(self) -> str:
        return self.screen.captions[self.lang]

    def url(self, variant: str) -> str:
        return self.screen.url(self.lang, variant)

    def dimensions(self, variant: str) -> tuple[int, int]:
        return self.screen.dimensions(variant)


def load_catalog(path: Path, languages: tuple[str, ...]) -> dict[str, Screen]:
    """A site without screens.yaml has no screenshot library."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise BuildError(f"{path}: expected a non-empty screenshot mapping")
    screens: dict[str, Screen] = {}
    for screen_id, item in data.items():
        if not isinstance(screen_id, str) or not SCREEN_ID_RE.fullmatch(screen_id):
            raise BuildError(f"{path}: invalid screen id {screen_id!r}")
        if not isinstance(item, dict) or set(item) != {"kind", "captions"}:
            raise BuildError(f"{path}: {screen_id} needs exactly kind and captions")
        if item["kind"] not in SOURCE_SIZES:
            raise BuildError(f"{path}: {screen_id} has unknown kind {item['kind']!r}")
        captions = item["captions"]
        if not isinstance(captions, dict) or set(captions) != set(languages):
            raise BuildError(f"{path}: {screen_id} needs captions for {', '.join(languages)}")
        if any(not isinstance(value, str) or not value.strip() for value in captions.values()):
            raise BuildError(f"{path}: {screen_id} has an empty caption")
        screens[screen_id] = Screen(screen_id, item["kind"], captions)
    return screens


def webp_dimensions(path: Path) -> tuple[int, int]:
    """Read the VP8 frame size emitted by the pinned lossy cwebp importer."""
    data = path.read_bytes()
    if len(data) < 30:
        raise BuildError(f"{path}: invalid lossy WebP file")
    riff_size, chunk_size = struct.unpack_from("<I", data, 4)[0], struct.unpack_from("<I", data, 16)[0]
    if (
        data[:4] != b"RIFF"
        or data[8:16] != b"WEBPVP8 "
        or data[23:26] != b"\x9d\x01\x2a"
        or riff_size != len(data) - 8
        or 20 + chunk_size + (chunk_size % 2) != len(data)
    ):
        raise BuildError(f"{path}: invalid lossy WebP file")
    width, height = struct.unpack_from("<HH", data, 26)
    return width & 0x3FFF, height & 0x3FFF


def check_asset(screen: Screen, lang: str, variant: str, output_dir: Path) -> None:
    path = output_dir / screen.path(lang, variant)
    if not path.is_file():
        raise BuildError(f"{path}: missing screenshot variant")
    actual = webp_dimensions(path)
    expected = screen.dimensions(variant)
    if actual != expected:
        raise BuildError(f"{path}: screenshot dimensions {actual}, expected {expected}")


class ScreenFigures(Treeprocessor):
    """Add the mobile link below each annotated h2; keep its id for TOC links."""

    def __init__(self, md, refs: tuple[ScreenRef, ...], open_label: str):
        super().__init__(md)
        self.refs = refs
        self.open_label = open_label

    def run(self, root: ET.Element) -> ET.Element:
        annotated = [node for node in root if node.tag == "h2" and "data-screen" in node.attrib]
        if len(annotated) != len(self.refs):
            raise BuildError("screen markers did not match rendered article headings")
        for heading, ref in zip(annotated, self.refs):
            if heading.get("data-screen") != ref.screen.id:
                raise BuildError("screen marker order changed while rendering Markdown")
            heading.set("data-screen-src", ref.url("phone"))
            heading.set("data-screen-alt", ref.caption)
            figure = ET.Element("figure", {"class": "article-screen-inline"})
            link = ET.SubElement(
                figure,
                "a",
                {
                    "href": ref.url("zoom"),
                    "class": "article-screen-link",
                    "aria-label": self.open_label.format(caption=ref.caption),
                    "data-zoom-width": str(ref.dimensions("zoom")[0]),
                    "data-zoom-height": str(ref.dimensions("zoom")[1]),
                },
            )
            width, height = ref.dimensions("mobile")
            ET.SubElement(
                link,
                "img",
                {
                    "src": ref.url("mobile"),
                    "alt": ref.caption,
                    "width": str(width),
                    "height": str(height),
                    "loading": "lazy",
                    "decoding": "async",
                },
            )
            root.insert(list(root).index(heading) + 1, figure)
        return root


class ScreenFigureExtension(Extension):
    def __init__(self, refs: tuple[ScreenRef, ...], open_label: str):
        super().__init__()
        self.refs = refs
        self.open_label = open_label

    def extendMarkdown(self, md) -> None:
        md.treeprocessors.register(ScreenFigures(md, self.refs, self.open_label), "screen_figures", 0)
