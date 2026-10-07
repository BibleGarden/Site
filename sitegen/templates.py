"""Shared cached Jinja environments for page and embedded component rendering."""
import json
from pathlib import Path
from functools import lru_cache
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape as html_escape
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
GENERATOR_META = '<meta name="generator" content="sitegen">'

def nl2br(value: str) -> Markup:
    return Markup("<br>".join(html_escape(line) for line in value.split("\n")))


def jsonld(value: object) -> Markup:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)
    return Markup(text.replace("</", "<\\/"))


@lru_cache(maxsize=2)
def make_environment(site_key: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader([TEMPLATES_DIR / site_key, TEMPLATES_DIR / "_shared"]),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["nl2br"] = nl2br
    env.filters["jsonld"] = jsonld
    env.globals["generator_meta"] = Markup(GENERATOR_META)
    return env
