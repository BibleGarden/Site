"""Content hashes on generated, copied and inline CSS/JS references."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from sitegen.assets import version_html
from sitegen.build import SiteBuilder, build_all
from sitegen.errors import BuildError

ROOT = Path(__file__).resolve().parent.parent


class AssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value and urlsplit(value).path.endswith((".css", ".js")):
                self.urls.append(value)


class AssetVersioningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.outputs = {}
        for preview in (False, True):
            output = Path(cls.directory.name) / ("preview" if preview else "public")
            build_all(preview=preview, output_root=output)
            cls.outputs[preview] = output

    def test_every_page_has_current_first_party_hashes(self) -> None:
        for preview, output in self.outputs.items():
            for site, origin in (("bible-garden", "https://bible.garden"), ("lampada", "https://lampada.app")):
                site_root = output / site
                assets = set()
                pages = sorted(site_root.rglob("*.html"))
                self.assertTrue(pages)
                for page in pages:
                    parser = AssetReferences()
                    parser.feed(page.read_text(encoding="utf-8"))
                    page_url = f"{origin}/{page.relative_to(site_root).as_posix()}"
                    for reference in parser.urls:
                        resolved = urlsplit(urljoin(page_url, reference))
                        if resolved.netloc != urlsplit(origin).netloc:
                            continue
                        with self.subTest(preview=preview, page=page, url=reference):
                            asset = site_root / unquote(resolved.path).lstrip("/")
                            expected = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
                            self.assertEqual(parse_qs(resolved.query).get("v"), [expected])
                            assets.add(resolved.path)
                expected_assets = {"/css/site.css", "/css/article.css", "/js/landing.js"} if site == "bible-garden" else {"/assets/styles.css", "/assets/site.js"}
                self.assertTrue(expected_assets <= assets)
                if site == "lampada":
                    self.assertIn("/assets/prayer-session-demo.css", assets)
                    self.assertIn("/assets/prayer-session-demo.js", assets)
                    index = (site_root / "articles/index.html").read_text()
                    self.assertNotIn("prayer-session-demo.js", index)
                if preview and site == "bible-garden":
                    self.assertIn("/js/gospel-today.js", assets)

    def test_changed_built_bytes_change_hash_and_inline_config_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "script.js"
            page = root / "index.html"
            html = '<script>const config = {"script": "/script.js"}; const url = `/script.js`;</script>'
            versions = []
            for payload in (b"first", b"second"):
                asset.write_bytes(payload)
                expected = hashlib.sha256(payload).hexdigest()[:12]
                result = version_html(html, page, root, "https://bible.garden")
                self.assertIn(f'"/script.js?v={expected}"', result)
                self.assertIn(f'`/script.js?v={expected}`', result)
                self.assertEqual(version_html(result, page, root, "https://bible.garden"), result)
                versions.append(result)
            self.assertNotEqual(*versions)

    def test_relative_absolute_and_existing_queries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "site.css").write_bytes(b"styles")
            digest = hashlib.sha256(b"styles").hexdigest()[:12]
            html = '''<link href="../site.css?theme=dark&amp;v=old#styles">
<link href="https://lampada.app/site.css?v=manual">
<script src="https://stats.bible.garden/script.js"></script>
<script src="//cdn.example.com/missing.js"></script>'''
            result = version_html(html, root / "privacy/index.html", root, "https://lampada.app")
            self.assertIn(f'../site.css?theme=dark&amp;v={digest}#styles', result)
            self.assertIn(f'https://lampada.app/site.css?v={digest}', result)
            self.assertIn('src="https://stats.bible.garden/script.js"', result)
            self.assertIn('src="//cdn.example.com/missing.js"', result)

    def test_build_fails_when_generated_page_asset_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            builder = SiteBuilder(ROOT / "content/bible-garden", Path(directory) / "site", preview=False)
            (builder.site.output_dir / "js/landing.js").unlink()
            with self.assertRaisesRegex(BuildError, "missing CSS/JS asset /js/landing.js"):
                builder.build()

    def test_build_fails_when_copied_page_asset_is_missing(self) -> None:
        copytree = shutil.copytree

        def copy_without_script(source, target, *args, **kwargs):
            result = copytree(source, target, *args, **kwargs)
            if Path(target).name == "assets":
                (Path(target) / "site.js").unlink()
            return result

        with tempfile.TemporaryDirectory() as directory:
            with patch("sitegen.build.shutil.copytree", side_effect=copy_without_script):
                with self.assertRaisesRegex(BuildError, "missing CSS/JS asset ../assets/site.js"):
                    SiteBuilder(ROOT / "content/lampada", Path(directory) / "site", preview=True).build()

    def test_missing_inline_config_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(BuildError, "missing CSS/JS asset /missing.js"):
                version_html('<script type="application/json">{"script": "/missing.js"}</script>', root / "index.html", root, "https://bible.garden")
