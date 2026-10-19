#!/usr/bin/env python3
"""Register verified, published Lampada citations in channel-ai."""

import argparse
import hashlib
import os
from pathlib import Path
import sys
from urllib.parse import quote

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sitegen.content import _frontmatter, REQUIRED_ARTICLE_KEYS, OPTIONAL_ARTICLE_KEYS, SLUG_RE
from sitegen.corpus import citations
from sitegen.errors import BuildError
from tools.check_corpus_citations import CheckError, CorpusAPI

ARTICLES = Path(__file__).resolve().parents[1] / "content/lampada/articles"
PREFIX = "site:lampada/articles/"


def fragment_hash(item, api, books):
    """Prove the old book/range anchor before asserting a current fragment hash."""
    book_id = item['book_id']
    if book_id not in books:
        books[book_id] = api.request(f'/books/{book_id}/text')
    book = books[book_id]
    text = book['text']
    if (book['text_sha256'] != item['text_sha256']
            or hashlib.sha256(text.encode('utf-8')).hexdigest() != item['text_sha256']):
        raise CheckError('Article is stale: book text changed or is corrupt; reanchor required '
                         '(tools/reanchor_corpus_sources.py)')
    hits = api.request('/search/chunks', {'ids': [item['chunk_id']]})['chunks']
    if len(hits) != 1 or hits[0]['chunk_id'] != item['chunk_id']:
        raise CheckError('Chunk lookup did not return the requested chunk; reanchor required')
    hit = hits[0]
    if (book['book']['id'] != book_id or hit['book']['id'] != book_id
            or hit['text_sha256'] != item['text_sha256']):
        raise CheckError('Chunk/book identity or hash mismatch; reanchor required')
    if not (0 <= hit['char_start'] <= item['char_start'] < item['char_end']
            <= hit['char_end'] <= len(text)):
        raise CheckError('Article is stale: citation range is outside current chunk; reanchor required')
    if hit['text'] != text[hit['char_start']:hit['char_end']]:
        raise CheckError('Chunk text does not match canonical book range')
    result = hashlib.sha256(hit['text'].encode('utf-8')).hexdigest()
    if 'chunk_text_sha256' in hit and hit['chunk_text_sha256'] != result:
        raise CheckError('Chunk text hash does not match exact fragment text')
    if not 1 <= len(item['chunk_id']) <= 255:
        raise CheckError('Chunk ID must contain 1..255 characters')
    return result


def plan(api, *, slug=None, articles=ARTICLES):
    """Finish every local and remote preflight read before returning any writes."""
    if not articles.is_dir():
        raise CheckError(f'Article directory does not exist: {articles}')
    if slug is not None and not SLUG_RE.fullmatch(slug):
        raise CheckError('Invalid article slug')
    directories = [articles / slug] if slug is not None else sorted(
        path for path in articles.iterdir() if path.name != '.gitkeep')
    published = {}
    snapshots = {}
    for directory in directories:
        if not directory.is_dir() or not SLUG_RE.fullmatch(directory.name):
            raise CheckError(f'Invalid or missing article directory: {directory}')
        source = PREFIX + directory.name
        if len(source) > 255:
            raise CheckError(f'Source exceeds 255 characters: {source}')
        paths = sorted(directory.iterdir())
        if not paths:
            raise CheckError(f'Article has no language versions: {directory}')
        for path in paths:
            if path.name not in {'ru.md', 'en.md', 'uk.md'} or not path.is_file():
                raise CheckError(f'Unexpected article language file: {path}')
            snapshots[path] = path.read_bytes()
            meta, body, _ = _frontmatter(path, REQUIRED_ARTICLE_KEYS,
                                         (*OPTIONAL_ARTICLE_KEYS, 'corpus_sources'))
            if 'draft' in meta and type(meta['draft']) is not bool:
                raise CheckError(f'{path}: draft must be a boolean')
            if meta.get('draft', False):
                continue
            items = citations(meta.get('corpus_sources', []), body, path)
            published.setdefault(source, []).extend((path, item) for item in items)

    operations = []
    books = {}
    for source, entries in sorted(published.items()):
        chunks = {}
        for path, item in entries:
            try:
                value = fragment_hash(item, api, books)
            except CheckError as exc:
                raise CheckError(f'{path} [{item["id"]}]: {exc}') from exc
            if item['chunk_id'] in chunks and chunks[item['chunk_id']] != value:
                raise CheckError(f'{source}: conflicting fragment hashes across citations/languages')
            chunks[item['chunk_id']] = value
        if len(chunks) > 10000:
            raise CheckError(f'{source}: exceeds the API limit of 10000 chunks')
        operations.append(('PUT', source, {'chunks': [
            {'chunk_id': cid, 'text_sha256': value} for cid, value in sorted(chunks.items())]}))
    if slug is None:
        existing = api.request('/external-usage')
        operations.extend(('DELETE', entry['source'], None) for entry in existing
                          if entry['source'].startswith(PREFIX) and entry['source'] not in published)
    for path, raw in snapshots.items():
        if path.read_bytes() != raw:
            raise CheckError(f'Article changed during preflight: {path}')
    return operations


def synchronize(api, operations, *, dry_run=False):
    for method, source, body in operations:
        path = '/external-usage/' + quote(source, safe='/')
        print(f'{method} {source}' + (f' ({len(body["chunks"])} chunks)' if body else ''))
        if dry_run:
            continue
        try:
            response = api.request(path, body, method=method)
            if method == 'PUT' and (response['source'] != source or any(
                    chunk['stale'] for chunk in response['chunks']) or
                    sorted((chunk['chunk_id'], chunk['text_sha256']) for chunk in response['chunks']) !=
                    sorted((chunk['chunk_id'], chunk['text_sha256']) for chunk in body['chunks'])):
                raise CheckError('PUT response does not match the requested complete set')
        except CheckError as exc:
            raise CheckError(f'{method} {source}: {exc}; synchronization stopped. Earlier operations '
                             'may have succeeded; there is no cross-source transaction. No retry performed.') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--slug', help='Published article slug (all published languages)')
    selection.add_argument('--all', action='store_true', help='Synchronize all published articles and remove orphan sources')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print the plan without writes')
    args = parser.parse_args(argv)
    try:
        api = CorpusAPI(os.getenv('CORPUS_API_URL', 'http://127.0.0.1:3018'), os.getenv('CORPUS_API_KEY'))
        operations = plan(api, slug=args.slug)
        synchronize(api, operations, dry_run=args.dry_run)
    except (CheckError, BuildError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
