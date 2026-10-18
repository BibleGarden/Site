"""Wrap the article FAQ section ('## ... {#faq}' up to the next h2) in its own <section>."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

FAQ_ID = "faq"
SECTION_CLASS = "article-faq"


class FaqSection(Treeprocessor):
    def run(self, root: ET.Element) -> None:
        children = list(root)
        start = next((index for index, node in enumerate(children) if node.tag == "h2" and node.get("id") == FAQ_ID), None)
        if start is None:
            return
        end = next(
            (
                index
                for index in range(start + 1, len(children))
                if children[index].tag == "h2" or children[index].get("class") == "footnote"
            ),
            len(children),
        )
        section = ET.Element("section", {"class": SECTION_CLASS, "aria-labelledby": FAQ_ID})
        section.text = section.tail = "\n"
        section.extend(children[start:end])
        for node in children[start:end]:
            root.remove(node)
        root.insert(start, section)


class FaqSectionExtension(Extension):
    def extendMarkdown(self, md) -> None:
        # After attr_list (8) assigns the heading id and screen figures (0) are placed below their h2.
        md.treeprocessors.register(FaqSection(md), "faq_section", -1)
