"""Bucket Lampada (prayer) Keyword Planner keywords by intent.

usage: python3 cluster_lampada.py en|ru|uk [min_volume]
Output reproduces table 2.4 of ../lampada-semantic-core-and-content-plan.md.
"""
import re
import sys
from collections import defaultdict

# Reads the TSV files next to this script (keyword<TAB>volume).
import csv, os


def load(lang):
    path = os.path.join(os.path.dirname(__file__), f"lampada-kp-{lang}.tsv")
    return {r[0]: int(r[1]) for r in list(csv.reader(open(path, encoding="utf-8"), delimiter="\t"))[1:]}

lang = sys.argv[1]
minvol = int(sys.argv[2]) if len(sys.argv) > 2 else 500
kp = load(lang)

EXCLUDE = {
    "en": r"\b(namaz|salat|salah|azan|adhan|muslim|islam|dua|ramadan|fajr|isha|maghrib|qibla|quran|prayer times?|prayer time app|"
          r"rosary|novena|chaplet|hail mary|our father|lord'?s prayer|catholic|saint|st\.|liturgy of the hours|divine office|lectio 365|hallow|"
          r"jewish|shema|hindu|buddhist|mantra|"
          r"prayer for [a-z ]+|prayers? (?:to|of) [a-z ]+|prayer request|pray for me|"
          r"printable|pdf|template|book|booklet|cards?|journal notebook|notebook|amazon|etsy|gift|"
          r"wallpaper|quotes|images?|pictures?|tattoo|coloring|kids|children|"
          r"lyrics|song|hymn|worship music|instrumental|"
          r"shower|hands|kneel|posture|clothing|tongues|"
          r"night prayer|morning prayer|evening prayer|bedtime|sleep|ibreviary|"
          r"bible verses for anxiety|scripture for anxiety|bible verses about prayer|praying scripture for healing|"
          r"prayer timer|meditation timer|"
          r"^gratitude (?:journal|journaling)$)\b",
    "ru": r"(молитв[аыуе]? (?:о|за|об|от|на|перед|после|при|к|в день|ангелу|николаю|матрон|спиридон|божьей|богородиц|иисусова)|"
          r"здрави|усопш|умерш|самоубий|четк|икон|святым|святому|старц|оптинск|серафим|саровск|ангелу хранителю|"
          r"утренн|вечерн|на сон|сон грядущ|перед едой|после еды|о здравии|благодарност|"
          r"молитвослов|канон|акафист|псалт|тропар|кондак|правило серафима|"
          r"католик|католич|намаз|мусульман|ислам|розари|"
          r"солиться|сало|лермонтов|читательск|стих|"
          r"скачать|картинк|текст|слушать|аудио|видео|"
          r"в церкви|в храме|руками|креститься|на коленях|платок)",
    "uk": r"(вервиц|вервич|розарі|новен|дев ятниц|акафіст|ісусова|таємниця щастя|померл|здоров|"
          r"угкц|скачати|молитва (?:до|за|про|на|перед)|католик|намаз|мусульман|ісламськ)",
}
BUCKETS = {
    "en": [
        ("app", r"\b(app|apps|application|android|iphone|ios)\b"),
        ("how-to-pray", r"\b(how to pray|how do (?:i|you|we) pray|how can i pray|learn to pray|start praying|begin praying|pray for beginners|pray properly|pray effectively|pray correctly|how should i pray|ways to pray|what is prayer)\b"),
        ("own-words", r"\b(own words|in my own words|talk to god|talking to god|conversation with god|speak to god)\b"),
        ("focus", r"\b(focus|distract|wander|concentrat|attention|mind)\b"),
        ("journal", r"\b(journal|journaling|diary|log)\b"),
        ("prompts-topics", r"\b(prompt|prompts|what to pray|things to pray|topics|ideas|list)\b"),
        ("routine-habit", r"\b(routine|habit|daily|every day|everyday|consistent|discipline|schedule|morning|night|bedtime|streak)\b"),
        ("timer-duration", r"\b(timer|how long|minutes|hour|hours|duration|length)\b"),
        ("methods", r"\b(acts|method|methods|structure|steps|framework|model|pattern|types of prayer|kinds of prayer|forms of prayer)\b"),
        ("scripture", r"\b(scripture|bible|verse|verses|psalm|word of god)\b"),
        ("meditation-quiet", r"\b(meditat|quiet time|silence|silent|contemplat|stillness|listening prayer|hear god|hearing god|god'?s voice|presence)\b"),
        ("music", r"\b(music|sound|ambient|background)\b"),
        ("reminder", r"\b(remind|reminder|notification|alarm)\b"),
        ("anxiety-emotions", r"\b(anxiety|anxious|stress|worry|fear|peace|depress|grief|lonely|angry|guilt)\b"),
    ],
    "ru": [
        ("app", r"(приложени|апп\b|андроид|айфон)"),
        ("how-to-pray", r"(как молит|как научиться|как правильно молит|как начать молит|как нужно молит|научиться молит|как молятся)"),
        ("own-words", r"(своими словами|свои слова|разговор с богом|говорить с богом|общение с богом)"),
        ("focus", r"(отвлек|рассеян|сосредоточ|внимани|мысли|блуждан)"),
        ("journal", r"(дневник|записыва|журнал)"),
        ("prompts-topics", r"(о чем молит|о чём молит|темы для|список молит|что просить|о чем просить)"),
        ("routine-habit", r"(правило|каждый день|ежедневн|привычк|регулярн|расписани|распорядок|утром|вечером)"),
        ("timer-duration", r"(таймер|сколько молит|как долго|сколько времени|минут|час\b|часа)"),
        ("methods", r"(метод|структур|шаги|этапы|виды молит|формы молит|типы молит)"),
        ("scripture", r"(писани|библи|стих|псал|слово божье|слову божьему)"),
        ("meditation-quiet", r"(медитац|тишин|тихое время|созерцан|услышать бога|голос бога|присутстви)"),
        ("music", r"(музык|звук|фон)"),
        ("reminder", r"(напомина|уведомлен)"),
        ("anxiety-emotions", r"(тревог|стресс|страх|беспокой|уныни|депресс|одиноч|обид|вин[аы]\b)"),
    ],
    "uk": [
        ("app", r"(додат|застосун|андроїд|айфон)"),
        ("how-to-pray", r"(як молит|як навчитися|як правильно молит|як почати молит|як потрібно молит)"),
        ("own-words", r"(своїми словами|розмова з богом|говорити з богом)"),
        ("focus", r"(відволік|розсіян|зосеред|уваг|думки)"),
        ("journal", r"(щоденник|записув|журнал)"),
        ("prompts-topics", r"(про що молит|теми для|список молит|що просити)"),
        ("routine-habit", r"(правило|щодня|кожен день|звичк|регулярн|вранці|ввечері)"),
        ("timer-duration", r"(таймер|скільки молит|як довго|хвилин|годин)"),
        ("methods", r"(метод|структур|кроки|етапи|види молит|форми молит)"),
        ("scripture", r"(писанн|біблі|вірш|псал|слово боже)"),
        ("meditation-quiet", r"(медитац|тиш|тихий час|споглядан|почути бога|голос бога)"),
        ("music", r"(музик|звук)"),
        ("reminder", r"(нагадув|сповіщен)"),
        ("anxiety-emotions", r"(тривог|стрес|страх|неспок|депрес|самотн)"),
    ],
}

ex = re.compile(EXCLUDE[lang], re.I)
buckets = defaultdict(list)
for k, v in kp.items():
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
    print(f"\n## {name}: {len(items)} keywords, sum {sum(v for v, _ in items)}")
    print("   " + " | ".join(f"{k} ({v})" for v, k in items if v >= minvol)[:1400])
