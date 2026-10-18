#!/usr/bin/env python3
"""Report exact corpus evidence migrations; apply only a revalidated saved report."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sitegen.content import REQUIRED_ARTICLE_KEYS, OPTIONAL_ARTICLE_KEYS, _frontmatter
from sitegen.corpus import citation_chapter, citations
from sitegen.errors import BuildError
from tools.check_corpus_citations import CheckError, CorpusAPI, normalize
from tools.corpus_judge import unique_object

ANCHORS = ("chunk_id", "char_start", "char_end", "text_sha256", "chapter")
METADATA = ("author", "title", "translator", "source_url")


class ManualReview(Exception):
    """A valid source needs an editorial decision rather than automatic relocation."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_article(path):
    before = path.read_bytes()
    meta, body, _ = _frontmatter(path, REQUIRED_ARTICLE_KEYS, (*OPTIONAL_ARTICLE_KEYS, "corpus_sources"))
    items = citations(meta.get("corpus_sources", []), body, path)
    if path.read_bytes() != before:
        raise CheckError(f"Article changed while reading: {path}")
    return before, items


class Migration:
    def __init__(self, snapshots, api):
        # The supplied directory is the backup root, never the live sidecar tree.
        self.snapshots = Path(snapshots).resolve()
        self.api = api
        self.old = {}
        self.current = {}
        self.inventory = None

    def old_text(self, book_id):
        if book_id not in self.old:
            base = self.snapshots / "data/lampada/texts" / f"book_{book_id}"
            metadata = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"),
                                  object_pairs_hook=unique_object)
            raw = base.with_suffix(".txt").read_bytes()
            if sha(raw) != metadata["text_sha256"]:
                raise CheckError("Old sidecar hash does not match its text snapshot")
            self.old[book_id] = (raw.decode("utf-8"), metadata["text_sha256"])
        return self.old[book_id]

    def current_book(self, book_id):
        if book_id in self.current:
            return self.current[book_id]
        if self.inventory is None:
            entries = self.api.request("/books")["books"]
            self.inventory = {entry["id"]: entry for entry in entries}
            if len(self.inventory) != len(entries):
                raise CheckError("Duplicate book IDs in inventory")
        entry = self.inventory.get(book_id)
        if entry is None or entry["status"] != "indexed" or entry["chunks_count"] < 1:
            raise CheckError("Book is not currently indexed")
        book = self.api.request(f"/books/{book_id}/text")
        if book["book"]["id"] != book_id or sha(book["text"].encode("utf-8")) != book["text_sha256"]:
            raise CheckError("Current canonical book identity/hash mismatch")
        chunks = []
        # channel-ai's explicit ID contract: book-{DB id}-{zero-based index:04d}.
        # Fetch the entire known inventory, not semantic search guesses.
        ids = [f"book-{book_id}-{i:04d}" for i in range(entry["chunks_count"])]
        for offset in range(0, len(ids), 100):
            batch = ids[offset:offset + 100]
            found = self.api.request("/search/chunks", {"ids": batch})["chunks"]
            if len(found) != len(batch) or {hit["chunk_id"] for hit in found} != set(batch):
                raise CheckError("Incomplete or duplicate current chunk inventory")
            for hit in found:
                start, end = hit["char_start"], hit["char_end"]
                if (hit["book"] != book["book"] or hit["text_sha256"] != book["text_sha256"]
                        or not 0 <= start < end <= len(book["text"])
                        or hit["text"] != book["text"][start:end]):
                    raise CheckError("Current chunk identity/hash/canonical range mismatch")
                citation_chapter(hit["citation_label"])
            chunks.extend(found)
        self.current[book_id] = book, chunks
        return book, chunks

    def source(self, item):
        book, chunks = self.current_book(item["book_id"])
        unchanged = book["text_sha256"] == item["text_sha256"]
        if unchanged:
            # A verified identical hash proves this is also the old canonical text.
            old, old_hash = book["text"], book["text_sha256"]
        else:
            old, old_hash = self.old_text(item["book_id"])
        start, end = item["char_start"], item["char_end"]
        if old_hash != item["text_sha256"] or not 0 <= start < end <= len(old):
            raise CheckError("Old evidence hash/range does not match snapshot")
        fragment = old[start:end]
        if item["kind"] == "quote" and normalize(item["original"]) not in normalize(fragment):
            raise ManualReview("Original quotation is absent from the old exact fragment")
        for key in METADATA:
            if book["book"][key] != item[key]:
                raise ManualReview(f"Source edition metadata changed: {key}; review manually")
        if not unchanged:
            if old.find(fragment) != start or old.find(fragment, start + 1) >= 0:
                raise ManualReview("Exact old fragment has ambiguous matches in the old text; review manually")
            start = book["text"].find(fragment)
            if start < 0:
                raise ManualReview("Exact old fragment was removed or edited; review manually")
            if book["text"].find(fragment, start + 1) >= 0:
                raise ManualReview("Exact old fragment has ambiguous matches in the new text; review manually")
            end = start + len(fragment)
        containing = [hit for hit in chunks if hit["char_start"] <= start < end <= hit["char_end"]]
        if len(containing) != 1:
            raise ManualReview("Range crosses a chunk boundary or has no unique containing chunk; review manually")
        hit = containing[0]
        context = self.api.request("/search/context", {"book_id": item["book_id"],
                                   "char_start": start, "char_end": end,
                                   "before": 0, "after": 0, "scope": "leaf"})
        if (context["book"] != book["book"] or context["text_sha256"] != book["text_sha256"]
                or context["char_start"] != start or context["char_end"] != end
                or context["text"] != fragment or context["citation_label"] != hit["citation_label"]):
            raise CheckError("Current context identity/hash/range/citation_label mismatch")
        return {"chunk_id": hit["chunk_id"], "char_start": start, "char_end": end,
                "text_sha256": book["text_sha256"], "chapter": citation_chapter(hit["citation_label"])}, unchanged


def plan(paths, snapshots, api):
    migration = Migration(snapshots, api)
    articles = []
    for path in paths:
        path = Path(path).resolve()
        raw, items = load_article(path)
        entries = []
        for item in items:
            entry = {"id": item["id"], "before": {key: item[key] for key in ANCHORS}}
            try:
                entry["after"], entry["text_unchanged"] = migration.source(item)
                entry["status"] = "ready"
            except ManualReview as exc:
                entry.update(status="manual", reason=str(exc))
            entries.append(entry)
        articles.append({"path": str(path), "sha256": sha(raw), "sources": entries})
    return articles


def patch_anchors(raw, entries):
    """Replace only anchor scalars, retaining prose and other YAML byte-for-byte."""
    text = raw.decode("utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", text, re.DOTALL)
    if match is None:
        raise CheckError("Article must contain YAML frontmatter delimited by '---' lines")
    document = yaml.compose(match.group(1))
    source_nodes = [value for key, value in document.value if key.value == "corpus_sources"]
    if not entries:
        return raw
    if len(source_nodes) != 1 or not isinstance(source_nodes[0], yaml.SequenceNode):
        raise CheckError("Expected one explicit corpus_sources sequence")
    changes = {entry["id"]: entry for entry in entries}
    edits = []
    for node in source_nodes[0].value:
        if not isinstance(node, yaml.MappingNode):
            raise CheckError("Expected explicit corpus source mappings")
        fields = {key.value: value for key, value in node.value}
        keys = {key.value: key for key, _ in node.value}
        if len(fields) != len(node.value) or "id" not in fields:
            raise CheckError("Duplicate or implicit source keys are not supported")
        ident = fields["id"].value
        if ident not in changes:
            raise CheckError(f"Article source ID {ident!r} is missing from the report")
        entry = changes.pop(ident)
        for key in ANCHORS:
            if entry["before"][key] == entry["after"][key]:
                continue
            value = fields[key]
            if (not isinstance(value, yaml.ScalarNode)
                    or not keys[key].end_mark.index <= value.start_mark.index < node.end_mark.index):
                raise CheckError("Anchors must be explicit scalars, without YAML aliases")
            replacement = json.dumps(entry["after"][key], ensure_ascii=False)
            if value.style in ("|", ">"):
                scalar = match.group(1)[value.start_mark.index:value.end_mark.index]
                ending = re.search(r"\r?\n\Z", scalar)
                if ending:
                    replacement += ending.group()
            edits.append((match.start(1) + value.start_mark.index,
                          match.start(1) + value.end_mark.index,
                          replacement))
    if changes:
        raise CheckError("Report source IDs do not match article")
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return text.encode("utf-8")


def apply_report(report, api):
    if report["schema"] != 1:
        raise CheckError("Unsupported migration report schema")
    articles = report["articles"]
    if not articles or len({entry["path"] for entry in articles}) != len(articles):
        raise CheckError("Expected non-empty, unique article paths")
    if any(source["status"] != "ready" for article in articles for source in article["sources"]):
        raise CheckError("Report contains manual cases; resolve them and generate a new report")
    paths = [Path(article["path"]) for article in articles]
    for path, article in zip(paths, articles):
        if sha(path.read_bytes()) != article["sha256"]:
            raise CheckError(f"Article changed since report: {path}")
    current = plan(paths, report["snapshots"], api)
    if current != articles:
        raise CheckError("Corpus or snapshots changed since report; generate a new report")
    prepared = []
    try:
        for path, article in zip(paths, articles):
            raw, items = load_article(path)
            if sha(raw) != article["sha256"]:
                raise CheckError(f"Article changed during revalidation: {path}")
            updated = patch_anchors(raw, article["sources"])
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".reanchor-", delete=False) as handle:
                staged = Path(handle.name)
                prepared.append((path, staged, article["sha256"]))
                handle.write(updated)
            staged.chmod(path.stat().st_mode & 0o777)
            changes = {entry["id"]: entry["after"] for entry in article["sources"]}
            expected_items = [{**item, **changes[item["id"]]} for item in items]
            _, staged_items = load_article(staged)
            if staged_items != expected_items:
                raise CheckError(f"Staged evidence differs from the planned anchor changes: {path}")
        # All files passed schema, semantic and SHA preflight during staging.
        for path, staged, expected in prepared:
            if sha(path.read_bytes()) != expected:
                raise CheckError(f"Article changed before write: {path}")
            os.replace(staged, path)
    finally:
        for _, staged, _ in prepared:
            staged.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("articles", nargs="*", type=Path)
    parser.add_argument("--snapshots", type=Path, help="Backup root containing data/lampada/texts/book_ID.{json,txt}")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", type=Path, help="Create a private JSON report; never writes articles")
    mode.add_argument("--apply", type=Path, help="Explicitly apply a saved, fully ready report after live revalidation")
    parser.add_argument("--base-url", default=os.getenv("CORPUS_API_URL", "http://127.0.0.1:3018"))
    args = parser.parse_args(argv)
    if args.report and (not args.snapshots or not args.articles):
        parser.error("--report requires --snapshots and explicit article paths")
    if args.apply and (args.snapshots or args.articles):
        parser.error("--apply takes article paths and snapshots from the saved report")
    root = Path(__file__).resolve().parents[1]
    artifact = (args.report or args.apply).resolve()
    if artifact.is_relative_to(root):
        parser.error("Private migration reports must stay outside the repository")
    try:
        api = CorpusAPI(args.base_url, os.getenv("CORPUS_API_KEY"))
        if args.apply:
            report = json.loads(artifact.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            if report["api_url"] != api.base_url:
                raise CheckError("Report API URL differs from the selected API")
            apply_report(report, api)
            print(f'Applied {len(report["articles"])} articles; run the citation checker with cache next')
            return 0
        articles = plan(args.articles, args.snapshots, api)
        report = {"schema": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "api_url": api.base_url, "snapshots": str(args.snapshots.resolve()), "articles": articles}
        with artifact.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
        manual = sum(source["status"] == "manual" for article in articles for source in article["sources"])
        print(f"Report: {artifact}; manual cases: {manual}; articles unchanged")
        return int(manual > 0)
    except (CheckError, BuildError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"Reanchor failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
