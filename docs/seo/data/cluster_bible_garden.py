"""Bucket bible.garden Keyword Planner keywords by intent.

usage: python3 cluster_bible_garden.py en|ru [min_volume]
Output reproduces table 2.4 of ../semantic-core-and-content-plan.md.
"""
import csv
import re
import sys
from collections import defaultdict

import os

lang = sys.argv[1]
minvol = int(sys.argv[2]) if len(sys.argv) > 2 else 500
path = os.path.join(os.path.dirname(__file__), f"bible-garden-kp-{lang}.tsv")
ideas = {r[0]: int(r[1]) for r in list(csv.reader(open(path, encoding="utf-8"), delimiter="\t"))[1:]}

EXCLUDE = {
    "en": r"\b(kjv|king james|niv|esv|nlt|nkjv|nasb|nrsv|csb|message|amplified|vulgate|tyndale|wycliffe|septuagint|geneva|douay|new world|jehovah|"
          r"psalm|psalms|proverbs|genesis|isaiah|jeremiah|matthew|john \d|romans|revelation|corinthians|ephesians|philippians|"
          r"tamil|telugu|tagalog|yoruba|malayalam|hindi|swahili|urdu|amharic|igbo|hausa|korean|chinese|arabic|french|german|portuguese|italian|"
          r"catholic|lds|mormon|torah|quran|koran|hebrew|greek|aramaic|latin|interlinear|strong'?s|concordance|commentary|"
          r"verse of the day|scripture of the day|daily verse|devotional|study bible|study guide|"
          r"pdf|printable|download|mp3|youtube|amazon|walmart|price|buy|cheap|leather|large print|hardcover|paperback|"
          r"youversion|you version|bible gateway|biblegateway|bible hub|biblehub|logos|olive tree|blue letter|dwell|bible\.is|"
          r"quiz|trivia|game|coloring|kids|children|toddler|baby|wedding|funeral|tattoo|meaning of)\b",
    "ru": r"(бондаренко|козлов|валаам|монастыр|иларион|голиков|дня\b|на сегодня|толкован|скачать|mp3|торрент|купить|цена|"
          r"псалом \d|псалмы \d|евангелие от|бытие|исход|откровение|притч|детск|ребен|викторин|тату|иврит|греческ|подстрочн|"
          r"коран|тора|мормон|свидетел|католич|перевод с английского|переводчик)",
}
BUCKETS = {
    "en": [
        ("audio-app", r"\b(app|apps|application|android|iphone|ios|apk)\b"),
        ("audio-listen", r"\b(audio|listen|listening|audiobook|narrat|read to me|reads to you|spoken)\b"),
        ("bilingual", r"\b(parallel|bilingual|two languages|multiple languages|different languages|multilingual|side by side|dual language)\b"),
        ("reading-plan-year", r"\b(in a year|one year|365|yearly|annual|in 1 year|in a yr)\b"),
        ("reading-plan", r"\b(reading plan|reading plans|reading schedule|plan to read|reading chart|reading tracker|tracker|checklist|reading calendar|read through|read the whole|read the entire)\b"),
        ("chronological", r"\bchronolog"),
        ("start-reading", r"\b(start reading|begin reading|beginner|beginners|first time|how to read|where to start|new to the bible|understand the bible)\b"),
        ("translations", r"\b(translation|translations|version|versions|accurate|literal|paraphrase|word for word)\b"),
        ("red-letter", r"\b(red letter|red letters|in red|words of jesus|words of christ)\b"),
        ("learn-language", r"\b(learn english|learn spanish|learn a language|learn languages|esl|language learning)\b"),
        ("offline", r"\b(offline|without internet|no internet)\b"),
        ("free-noads", r"\b(free|without ads|no ads|ad free|ad-free|open source)\b"),
        ("how-long", r"\b(how long|how many hours|how many days|how many chapters|how many words|how many pages|time to read)\b"),
        ("order-of-books", r"\b(order|in order|books of the bible)\b"),
        ("new-testament", r"\b(new testament|old testament|gospels)\b"),
    ],
    "ru": [
        ("audio-app", r"(приложени|андроид|айфон|iphone|телефон|apk)"),
        ("audio-listen", r"(слушать|аудио|аудиокниг|озвуч|читает|слушаем)"),
        ("bilingual", r"(английск|двух язык|параллельн|украинск|нескольких язык|двуязычн)"),
        ("reading-plan-year", r"(за год|на год|365|годов)"),
        ("reading-plan", r"(план чтения|график чтения|на каждый день|читать по плану|расписани|трекер)"),
        ("chronological", r"хронолог"),
        ("start-reading", r"(с чего начать|как читать|как правильно читать|начать читать|начинающ|новичк|понять библию|как изучать|изучение библии)"),
        ("translations", r"(перевод|синодальн|кулаков|рбо|заокск|современн)"),
        ("red-letter", r"(красн)"),
        ("learn-language", r"(английский по|учить английск|изучение английск)"),
        ("offline", r"(оффлайн|офлайн|без интернета)"),
        ("free-noads", r"(бесплатно|без рекламы)"),
        ("how-long", r"(сколько времени|сколько часов|сколько дней|сколько глав|сколько книг|сколько страниц)"),
        ("order-of-books", r"(в каком порядке|порядок|книги библии|состав библии|структура)"),
        ("new-testament", r"(новый завет|ветхий завет|евангели|псалт)"),
    ],
}

ex = re.compile(EXCLUDE[lang], re.I)
buckets = defaultdict(list)
for k, v in ideas.items():
    if ex.search(k):
        buckets["_excluded"].append((v, k))
        continue
    for name, pat in BUCKETS[lang]:
        if re.search(pat, k, re.I):
            buckets[name].append((v, k))
            break
    else:
        buckets["_other"].append((v, k))

for name, _ in BUCKETS[lang] + [("_other", ""), ("_excluded", "")]:
    items = sorted(buckets[name], reverse=True)
    total = sum(v for v, _ in items)
    print(f"\n## {name}: {len(items)} keywords, sum {total}")
    shown = [f"{k} ({v})" for v, k in items if v >= minvol][:40]
    print("   " + " | ".join(shown))
