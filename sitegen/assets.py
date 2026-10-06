"""Content versions for local CSS/JS URLs in HTML, including inline JS/config."""

from __future__ import annotations

import hashlib
import re
from html import unescape
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

from .errors import BuildError

ASSET_URL_RE = re.compile(
    r'''(?P<quote>["'`])(?P<url>[^\s"'`<>]+?\.(?:css|js)(?:[?#][^\s"'`<>]*)?)(?P=quote)'''
)


def version_html(html: str, page: Path, output_dir: Path, base_url: str) -> str:
    """Hash the built bytes; keep paths, other query parameters and fragments.

    URLs are rewritten after rendering so attributes and literal URLs inside
    inline scripts/JSON receive the same versions as copied static pages.
    External URLs are left intact. A missing local asset is a build error.
    """
    root = output_dir.resolve()
    page_url = f"{base_url}/{page.relative_to(output_dir).as_posix()}"
    origin = urlsplit(base_url).netloc

    def replace(match: re.Match[str]) -> str:
        original = match["url"]
        reference = unescape(original)
        resolved = urlsplit(urljoin(page_url, reference))
        if resolved.scheme not in {"http", "https"} or resolved.netloc != origin:
            return match[0]
        asset = (root / unquote(resolved.path).lstrip("/")).resolve()
        if not asset.is_relative_to(root) or not asset.is_file():
            raise BuildError(f"{page}: missing CSS/JS asset {reference}")
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        url = urlsplit(reference)
        query = [(key, value) for key, value in parse_qsl(url.query, keep_blank_values=True) if key != "v"]
        query.append(("v", digest))
        versioned = urlunsplit(url._replace(query=urlencode(query)))
        if "&amp;" in original:
            versioned = versioned.replace("&", "&amp;")
        return f'{match["quote"]}{versioned}{match["quote"]}'

    return ASSET_URL_RE.sub(replace, html)
