"""Explicitly refresh the committed rights snapshot from GET /api/rights."""

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sitegen.errors import BuildError
from sitegen.rights import validate_registry


def fetch_registry(url: str, api_key: str) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise BuildError("use HTTPS or a local HTTP server")
    if not api_key.strip():
        raise BuildError("RIGHTS_API_KEY must contain an ordinary catalog API key")
    request = Request(url, headers={"X-API-Key": api_key, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except (URLError, ValueError) as error:
        raise BuildError("rights API request failed; snapshot was not changed") from error
    return validate_registry(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://api.bible.garden/api/rights")
    args = parser.parse_args()
    data = fetch_registry(args.url, os.environ.get("RIGHTS_API_KEY", ""))
    path = ROOT / "content/bible-garden/rights.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Refreshed {len(data['items'])} rights entries from /api/rights")


if __name__ == "__main__":
    try:
        main()
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
