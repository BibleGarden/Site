"""Offline rendering and validation of the derived rights catalog."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from markupsafe import escape

from sitegen.build import SiteBuilder
from sitegen.errors import BuildError
from sitegen.rights import load_registry, validate_registry
from tools.refresh_rights import fetch_registry

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content/bible-garden"


class RightsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_registry(CONTENT / "rights.json")

    def test_snapshot_requires_supported_schema_and_template_fields(self):
        mutations = [
            lambda data: data.update(schema_version=2),
            lambda data: data.pop("items"),
            lambda data: data["items"]["text:npu"].pop("credit"),
            lambda data: data["items"]["text:npu"]["title"].pop("uk"),
            lambda data: data["items"]["text:npu"]["license"].pop("url"),
        ]
        for mutate in mutations:
            data = deepcopy(self.data)
            mutate(data)
            with self.subTest(mutation=mutate), self.assertRaises(BuildError):
                validate_registry(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            with self.assertRaises(BuildError):
                load_registry(path)
            path.write_text("{")
            with self.assertRaises(BuildError):
                load_registry(path)

    def test_pages_render_full_notices_without_network_or_javascript(self):
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", side_effect=AssertionError("offline build")):
            builder = SiteBuilder(CONTENT, Path(directory) / "bible-garden", preview=False)
            for lang in ("en", "ru", "uk"):
                builder.build_page("rights", lang)
                path = builder.output_path(lang, "rights/index.html")
                html = path.read_text(encoding="utf-8")
                prefix = "" if lang == "en" else lang + "/"
                self.assertIn(f'href="https://bible.garden/{prefix}rights/"', html)
                self.assertIn('id="text-npu"', html)
                self.assertIn('id="audio-bsb-bsb_souer"', html)
                self.assertIn("Copyright © 2022 by Biblica, Inc.", html)
                npu = html.split('aria-labelledby="text-npu"', 1)[1].split("</section>", 1)[0]
                for forbidden in ("Biblica®", "Бібліка®", "™", "Used with permission"):
                    self.assertNotIn(forbidden, npu)
                labels = builder.t(lang)["rights_page"]
                self.assertIn(f"<strong>{labels['rights_holder']}</strong> Biblica, Inc.", npu)
                for item in self.data["items"].values():
                    self.assertIn(str(escape(item["credit"][lang])), html)
                bsb = html.split('aria-labelledby="text-bsb"', 1)[1].split("</section>", 1)[0]
                self.assertIn(f"<strong>{labels['credit']}</strong>", bsb)
                self.assertNotIn(f"<strong>{labels['rights_holder']}</strong>", bsb)
                self.assertIn('href="https://creativecommons.org/licenses/by-sa/4.0/"', html)
                self.assertIn(self.data["items"]["text:npu"]["changes"][lang], html)
                for language in ("en", "ru", "uk"):
                    self.assertIn(f'hreflang="{language}"', html)
                footer = html.split("<footer", 1)[1]
                self.assertIn(f'href="/{prefix}rights/"', footer)

    def permission_registry(self):
        item = deepcopy(self.data["items"]["text:npu"])
        item.update(
            rights_holder="Example Rights Holder",
            license=None,
            public_domain_basis=None,
            permission={
                "en": "Used with written permission of Example Rights Holder; no voice cloning.",
                "ru": "Используется с письменного разрешения правообладателя; клонирование голоса запрещено.",
                "uk": "Використовується з письмового дозволу правовласника; клонування голосу заборонено.",
            },
        )
        audio = deepcopy(item)
        audio.update(kind="audio", voice_alias="example")
        return {"schema_version": 1, "items": {"text:example": item, "audio:example:example": audio}}

    def test_permission_renders_in_every_language(self):
        data = validate_registry(self.permission_registry())
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", side_effect=AssertionError("offline build")):
            builder = SiteBuilder(CONTENT, Path(directory) / "bible-garden", preview=False)
            builder.rights = data
            for lang, label in (("en", "Permission:"), ("ru", "Разрешение:"), ("uk", "Дозвіл:")):
                with self.subTest(lang=lang):
                    builder.build_page("rights", lang)
                    html = builder.output_path(lang, "rights/index.html").read_text(encoding="utf-8")
                    labels = builder.t(lang)["rights_page"]
                    for item_id, item in data["items"].items():
                        section = html.split(f'aria-labelledby="{item_id.replace(":", "-")}"', 1)[1].split("</section>", 1)[0]
                        self.assertIn(f"<strong>{label}</strong> {escape(item['permission'][lang])}", section)
                        self.assertIn(f"<strong>{labels['rights_holder']}</strong> Example Rights Holder", section)
                        self.assertNotIn(f"<strong>{labels['license']}</strong>", section)
                        self.assertNotIn(f"<strong>{labels['public_domain']}</strong>", section)

    def test_snapshot_accepts_absent_or_null_permission(self):
        for permission_present in (False, True):
            with self.subTest(permission_present=permission_present):
                data = deepcopy(self.data)
                for item in data["items"].values():
                    if permission_present:
                        item["permission"] = None
                    else:
                        item.pop("permission", None)
                self.assertEqual(validate_registry(data), data)

    def test_snapshot_requires_exactly_one_rights_basis(self):
        for bases in ((), ("license", "public_domain_basis"), ("license", "permission"), ("public_domain_basis", "permission")):
            with self.subTest(bases=bases):
                data = self.permission_registry()
                item = data["items"]["text:example"]
                values = {
                    "license": self.data["items"]["text:npu"]["license"],
                    "public_domain_basis": item["permission"],
                    "permission": item["permission"],
                }
                item.update({field: value if field in bases else None for field, value in values.items()})
                with self.assertRaisesRegex(BuildError, "text:example: expected exactly one"):
                    validate_registry(data)

    def test_permission_requires_every_localization(self):
        for lang in ("en", "ru", "uk"):
            for value in (None, "", " ", 123):
                with self.subTest(lang=lang, value=value):
                    data = self.permission_registry()
                    notice = data["items"]["text:example"]["permission"]
                    if value is None:
                        notice.pop(lang)
                    else:
                        notice[lang] = value
                    with self.assertRaisesRegex(BuildError, "text:example: missing EN/RU/UK permission"):
                        validate_registry(data)
        data = self.permission_registry()
        data["items"]["text:example"]["permission"] = "Not localized"
        with self.assertRaisesRegex(BuildError, "missing EN/RU/UK permission"):
            validate_registry(data)

    def test_permission_requires_rights_holder(self):
        for holder in (None, "", " ", 123):
            with self.subTest(holder=holder):
                data = self.permission_registry()
                data["items"]["text:example"]["rights_holder"] = holder
                with self.assertRaisesRegex(BuildError, "text:example: permission requires rights_holder"):
                    validate_registry(data)

    def test_refresh_uses_endpoint_and_validates_before_accepting_data(self):
        with patch("tools.refresh_rights.urlopen") as opener:
            response = opener.return_value.__enter__.return_value
            response.read.return_value = json.dumps(self.data).encode()
            self.assertEqual(fetch_registry("https://api.example.org/api/rights", "test-key"), self.data)
            self.assertEqual(fetch_registry("https://api.example.org/proxy/rights?version=1", "test-key"), self.data)
            self.assertEqual(fetch_registry("http://localhost:8080/api/rights/", "test-key"), self.data)
            request = opener.call_args.args[0]
            self.assertEqual(request.get_header("X-api-key"), "test-key")
            response.read.return_value = b'{"schema_version":2}'
            with self.assertRaises(BuildError):
                fetch_registry("https://api.example.org/api/rights", "test-key")
        for url, key in (("http://api.example.org/api/rights", "key"), ("https://api.example.org/api/rights", "")):
            with self.subTest(url=url), self.assertRaises(BuildError):
                fetch_registry(url, key)


if __name__ == "__main__":
    unittest.main()
