#!/usr/bin/env python3
"""Collect bounded Lampada search candidates, not publication-ready citations."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sitegen.corpus import citation_chapter


class ResearchError(Exception):
    pass


class CorpusAPI:
    def __init__(self, url, key):
        if not key:
            raise ResearchError("CORPUS_API_KEY is required")
        self.url = url.rstrip("/") + "/api/v1/channels/lampada"
        self.key = key

    def request(self, path, data=None):
        request = Request(
            self.url + path,
            data=None if data is None else json.dumps(data).encode("utf-8"),
            headers={"X-API-Key": self.key, "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise ResearchError(f"Corpus HTTP {exc.code}; no retry or substitution") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise ResearchError("Corpus unavailable or invalid JSON") from exc


def load_queries(path):
    queries = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"query", "limit", "min_score", "book_id", "author", "tradition", "license", "language"}
    if not isinstance(queries, list) or not queries:
        raise ResearchError("Queries must be a non-empty JSON list of search request objects")
    for query in queries:
        if (not isinstance(query, dict) or not isinstance(query.get("query"), str)
                or not query["query"].strip() or set(query) - allowed):
            raise ResearchError("Each query needs non-empty query text and supported API fields only")
    return queries


def collect(api, queries, max_per_book=2, max_hits=12, query_delay=0):
    inventory = api.request("/books")["books"]
    candidates = {}
    counts = []
    for number, query in enumerate(queries, 1):
        if number > 1 and query_delay:
            time.sleep(query_delay)
        try:
            hits = api.request("/search", query)["results"]
        except ResearchError as exc:
            raise ResearchError(f"Search query {number} failed: {exc}") from exc
        counts.append(len(hits))
        for hit in hits:
            try:
                citation_chapter(hit["citation_label"])
            except (KeyError, ValueError) as exc:
                raise ResearchError("Missing or invalid citation_label; refresh the corpus index") from exc
            key = (hit["book"]["id"], hit["section_index"])
            previous = candidates.get(key)
            matched = {number} if previous is None else previous["queries"] | {number}
            if previous is None or hit["score"] > previous["hit"]["score"]:
                candidates[key] = {"hit": hit, "queries": matched}
            else:
                previous["queries"] = matched
    if not candidates:
        raise ResearchError("No hits; revise the brief or queries explicitly")
    selected = []
    per_book = {}
    for candidate in sorted(candidates.values(), key=lambda c: (-c["hit"]["score"], c["hit"]["chunk_id"])):
        book_id = candidate["hit"]["book"]["id"]
        if per_book.get(book_id, 0) >= max_per_book:
            continue
        selected.append(candidate)
        per_book[book_id] = per_book.get(book_id, 0) + 1
        if len(selected) == max_hits:
            break
    return inventory, selected, counts


def md(value):
    if value is None or value == "":
        return "не указано в API"
    return re.sub(r"([\\`*_{}\[\]<>|#])", r"\\\1", " ".join(str(value).split()))


def excerpt_around_match(text, queries, limit):
    """Locate a lexical sentence match; semantic search supplies no sentence offsets."""
    stopwords = set(("the and for with from when how did you your "
                     "что как для это при его она они que les des une est avec").split())

    def terms(value):
        return {word[:4] for word in re.findall(r"[^\W\d_]{3,}", value.casefold())
                if word not in stopwords}

    wanted = set().union(*(terms(query) for query in queries))
    sentences = list(re.finditer(r"[^.!?…\n]+(?:[.!?…]+[»\"’”]*|$)", text))
    ranked = [(len(terms(match.group()) & wanted), match) for match in sentences]
    if not ranked or max(score for score, _ in ranked) == 0:
        return None
    _, best = max(ranked, key=lambda pair: (pair[0], -pair[1].start()))
    start, end = best.span()
    while start < end and text[start].isspace():
        start += 1
    if end - start > limit:
        # Keep the matching words visible when a source sentence exceeds the cap.
        words = list(re.finditer(r"[^\W\d_]{3,}", text[start:end]))
        anchor = next(word for word in words if word.group().casefold()[:4] in wanted)
        start = max(start, start + anchor.start() - limit // 3)
        end = min(end, start + limit)
    return text[start:end]


def render(topic, queries, inventory, selected, counts, excerpt_chars=180):
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [f"# Досье: {md(topic)}", "", f"Снято: {stamp}. Канал: lampada.", "",
             "Статус: кандидаты; Мария ещё не утвердила. Это исследование, не статья.",
             "Короткие выдержки нужны для выбора источников; контекст и полные тексты в git не сохраняем.", "",
             "## Запросы", "", "Точные POST /search payload; число результатов до дедупликации:", ""]
    for number, (query, count) in enumerate(zip(queries, counts), 1):
        lines += [f"{number}. `{json.dumps(query, ensure_ascii=False)}` — {count}."]
    lines += ["", "## Снимок доступности", "", "GET /books; статус API не доказывает полноту реестра lampada-books.md.", ""]
    for book in inventory:
        lines += [f'- book_id {book["id"]}: {md(book["author"])} — {md(book["title"])}; '
                  f'статус: {md(book["status"])}.']
    lines += ["", "## Кандидаты", "", "Один лучший hit на (book_id, section_index), затем ограничение на книгу и общий лимит.",
              "Score — близость к запросу, не качество и не редакционное одобрение.", ""]
    for number, candidate in enumerate(selected, 1):
        hit = candidate["hit"]
        book = hit["book"]
        excerpt = excerpt_around_match(
            hit["text"], [queries[i - 1]["query"] for i in candidate["queries"]], excerpt_chars
        )
        lines += [f'### {number}. {md(book["title"])}', "",
                  f'- Автор: {md(book["author"])}; традиция: {md(book["tradition"])}; язык: {md(book["language"])}.',
                  f'- Глава: {md(hit["citation_label"]) if hit["citation_label"] else "нет подтверждённой метки"}; '
                  f'раздел: {md(hit["section_path"])}; section_index: {hit["section_index"]}.',
                  f'- chunk_id: `{hit["chunk_id"]}`; book_id: {book["id"]}; score: {hit["score"]}.',
                  f'- Диапазон чанка: [{hit["char_start"]}, {hit["char_end"]}); text_sha256: `{hit["text_sha256"]}`.',
                  f'- Источник: {md(book["source_url"])}; лицензия: {md(book["license"])}; переводчик издания: {md(book["translator"])}.',
                  f'- Раздел найден запросами: {", ".join(map(str, sorted(candidate["queries"])))}.',
                  '- Почему кандидат: совпадение с запросом; смысл, опыт и пригодность подтвердить после чтения контекста.',
                  '- Выдержка (предложение вокруг лучшего буквального совпадения; длинное ограничено лимитом; не готовая цитата):', "",
                  f'> {md(excerpt) if excerpt is not None else "Нет буквального совпадения; выбрать фрагмент после чтения контекста."}', ""]
    lines += ["## Перед решением Марии", "",
              "- Прочитать /search/context с scope=chapter; для книги без структуры при 422 явно запросить scope=leaf; контекст хранить вне git.",
              "- Пустая citation_label допустима: chapter: null, сноска по книге. Явно неверная метка (сырой путь, повтор названия книги) — стоп и сообщение владельцу корпуса; не исправлять в Site и не подставлять структурный chapter.",
              "- Выбрать не менее трёх книг разных авторов, желательно разных традиций; описать зачем каждый фрагмент и ограничения.",
              "- Уточнить узкие диапазоны для будущих corpus_sources; текущие диапазоны относятся к целым чанкам.",
              "- Записать решение Марии и утверждённые chunk_id. До этого текст не писать.", ""]
    return "\n".join(lines)


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Explicitly replace an existing dossier")
    parser.add_argument("--api-url", default=os.environ.get("CORPUS_API_URL", "http://127.0.0.1:3018"))
    parser.add_argument("--query-delay", type=int, choices=range(31), default=0, metavar="0..30",
                        help="Seconds between queries; no retries")
    parser.add_argument("--max-per-book", type=positive, default=2)
    parser.add_argument("--max-hits", type=positive, default=12)
    parser.add_argument("--excerpt-chars", type=int, choices=range(1, 301), default=180, metavar="1..300")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.force:
            raise ResearchError("Output already exists; choose a new file or explicitly use --force")
        queries = load_queries(args.queries)
        api = CorpusAPI(args.api_url, os.environ.get("CORPUS_API_KEY"))
        inventory, selected, counts = collect(api, queries, args.max_per_book, args.max_hits, args.query_delay)
        dossier = render(args.topic, queries, inventory, selected, counts, args.excerpt_chars)
        with args.output.open("w" if args.force else "x", encoding="utf-8") as output:
            output.write(dossier)
    except (ResearchError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Research failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(selected)} candidates to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
