"""Lampada landing: committed screenshots, hero carousel and step sections."""

from __future__ import annotations

import re
import shutil
from html import unescape
import tempfile
import unittest
from pathlib import Path

from sitegen.build import SiteBuilder
from sitegen.errors import BuildError
from sitegen.landing_screens import ASSET_DIR, HEIGHT, SCREENS, WIDTH, load_landing_screens

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content/lampada"
STATIC = ROOT / "static/lampada"
CHECKSUMS = CONTENT / "landing-screens.sha256"
LANGUAGES = ("en", "ru", "uk")


class LandingScreenAssetsTest(unittest.TestCase):
    def test_committed_screens_load_in_carousel_order(self) -> None:
        screens = load_landing_screens(STATIC, CHECKSUMS, LANGUAGES)
        self.assertEqual(set(screens), set(LANGUAGES))
        self.assertEqual(tuple(screens["ru"]), SCREENS)
        self.assertEqual(screens["uk"]["home"].url, "/assets/screens/home.uk.webp")
        self.assertEqual((screens["en"]["home"].width, screens["en"]["home"].height), (WIDTH, HEIGHT))

    def test_changed_missing_or_extra_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            static = Path(directory) / "static"
            shutil.copytree(STATIC / ASSET_DIR, static / ASSET_DIR)
            checksums = Path(directory) / "landing-screens.sha256"
            shutil.copy2(CHECKSUMS, checksums)
            target = static / ASSET_DIR / "home.ru.webp"
            original = target.read_bytes()

            target.write_bytes(original[:-2] + bytes([original[-2] ^ 1]) + original[-1:])
            with self.assertRaisesRegex(BuildError, "checksum differs"):
                load_landing_screens(static, checksums, LANGUAGES)
            target.write_bytes(b"not a webp" * 4)
            with self.assertRaisesRegex(BuildError, "invalid lossy WebP"):
                load_landing_screens(static, checksums, LANGUAGES)
            target.unlink()
            with self.assertRaisesRegex(BuildError, r"missing=\['assets/screens/home.ru.webp'\]"):
                load_landing_screens(static, checksums, LANGUAGES)
            target.write_bytes(original)
            (static / ASSET_DIR / "stale.ru.webp").write_bytes(original)
            with self.assertRaisesRegex(BuildError, "extra=.*stale.ru.webp"):
                load_landing_screens(static, checksums, LANGUAGES)
            (static / ASSET_DIR / "stale.ru.webp").unlink()
            checksums.write_text(checksums.read_text(encoding="utf-8").splitlines(keepends=True)[0] * 2, encoding="utf-8")
            with self.assertRaisesRegex(BuildError, "duplicate"):
                load_landing_screens(static, checksums, LANGUAGES)


class LandingPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        builder = SiteBuilder(CONTENT, Path(cls.directory.name) / "lampada", preview=False)
        cls.pages = {}
        for lang in LANGUAGES:
            builder.build_landing(lang)
            cls.pages[lang] = builder.output_path(lang, "index.html").read_text(encoding="utf-8")
        cls.i18n = builder.site.i18n

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def test_carousel_shows_localized_screens_with_first_in_front(self) -> None:
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                html = self.pages[lang]
                slides = re.findall(r'<div class="coverflow-slide"[^>]*data-pos="([^"]+)"([^>]*)>\s*<img src="([^"]+)"[^>]*alt="([^"]+)"([^>]*)>', html)
                self.assertEqual([url for _, _, url, _, _ in slides], [f"/assets/screens/{screen}.{lang}.webp" for screen in SCREENS])
                self.assertEqual([pos for pos, *_ in slides], ["0", "1", "2", "hidden", "hidden", "hidden", "-2", "-1"])
                self.assertNotIn("aria-hidden", slides[0][1])
                self.assertTrue(all('aria-hidden="true"' in rest for _, rest, *_ in slides[1:]))
                self.assertIn('fetchpriority="high"', slides[0][4])
                self.assertTrue(all('loading="lazy"' in slide[4] for slide in slides[1:]))
                self.assertEqual([unescape(alt) for *_, alt, _ in slides], [self.i18n[lang]["landing"]["screens"][screen] for screen in SCREENS])
                dots = re.findall(r'<button type="button" class="coverflow-dot" aria-label="([^"]+)"[^>]*hidden>', html)
                position = self.i18n[lang]["landing"]["hero"]["screen_position"]
                self.assertEqual(dots, [position.format(n=n, total=len(SCREENS)) for n in range(1, len(SCREENS) + 1)])
                self.assertIn('src="/assets/landing.js?v=', html)

    def test_steps_reuse_carousel_images(self) -> None:
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                html = self.pages[lang]
                steps = re.findall(r'<h3 class="step-title">([^<]+)</h3>.*?<img src="([^"]+)"[^>]*loading="lazy"', html, re.DOTALL)
                self.assertEqual([url for _, url in steps], [f"/assets/screens/{screen}.{lang}.webp" for screen in SCREENS])
                self.assertEqual([unescape(title) for title, _ in steps], [self.i18n[lang]["landing"]["steps"][screen]["title"] for screen in SCREENS])

    def test_store_buttons_and_no_old_mockup(self) -> None:
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                html = self.pages[lang]
                self.assertIn(f'href="https://apps.apple.com/app/lampada/id6806024678?l={lang}" data-umami-event="app-store-click"', html)
                google_play = re.search(r'<span class="store-soon">.*?</span>\s*</span>', html, re.DOTALL).group(0)
                self.assertIn(self.i18n[lang]["landing"]["hero"]["google_play"], google_play)
                self.assertNotIn("href", google_play)
                self.assertNotIn("play.google.com", html)
                for removed in ("phone-top", "flame-wrap", "orbit", 'class="feature'):
                    self.assertNotIn(removed, html)


if __name__ == "__main__":
    unittest.main()
