"""Build the deterministic 365-day Bible reading plan from chapter audio lengths."""

from __future__ import annotations

import json
import sys
from bisect import bisect_left, bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sitegen.reading_plan import (  # noqa: E402
    PLAN_PATH, SEQUENTIAL_PLAN_PATH, load_chapters, range_data, reading_units,
    streams, validate_plan, validate_sequential_plan,
)


MAX_ALTERNATIONS = 8


def partition_uniform(chapters: list, days: int = 365) -> list[list]:
    """Exact minimax, then minimum squared deviation under that fixed bound."""
    count = len(chapters)
    if type(days) is not int or days < 1 or count < days:
        raise ValueError("not enough chapters for non-empty days")
    prefix = [0]
    for chapter in chapters:
        if type(chapter.tenths) is not int or chapter.tenths <= 0:
            raise ValueError("chapter duration must be a positive integer")
        prefix.append(prefix[-1] + chapter.tenths)
    total = prefix[-1]

    def bounds(limit: int) -> list[tuple[int, int]]:
        lower = max(1, (total - limit + days - 1) // days)
        upper = (total + limit) // days
        return [
            (bisect_left(prefix, prefix[end] - upper, 0, end),
             bisect_right(prefix, prefix[end] - lower, 0, end))
            for end in range(count + 1)
        ]

    def feasible(limit: int) -> bool:
        intervals = bounds(limit)
        previous = [False] * (count + 1)
        previous[0] = True
        for day in range(1, days + 1):
            accumulated = [0]
            for reachable in previous:
                accumulated.append(accumulated[-1] + reachable)
            current = [False] * (count + 1)
            for end in range(day, count - days + day + 1):
                first, last = intervals[end]
                current[end] = first < last and accumulated[last] > accumulated[first]
            previous = current
        return previous[count]

    low, high = 0, total * days
    while low < high:
        middle = (low + high) // 2
        if feasible(middle):
            high = middle
        else:
            low = middle + 1
    intervals = bounds(low)
    previous = [None] * (count + 1)
    previous[0] = 0
    parents = [[-1] * (count + 1)]
    for day in range(1, days + 1):
        current = [None] * (count + 1)
        parent = [-1] * (count + 1)
        for end in range(day, count - days + day + 1):
            first, last = intervals[end]
            for start in range(first, last):
                if previous[start] is None:
                    continue
                deviation = (prefix[end] - prefix[start]) * days - total
                candidate = previous[start] + deviation * deviation
                if current[end] is None or candidate < current[end]:
                    current[end], parent[end] = candidate, start
        previous = current
        parents.append(parent)
    if previous[count] is None:
        raise ValueError("could not partition chapters")
    chunks = []
    end = count
    for day in range(days, 0, -1):
        start = parents[day][end]
        if start < 0 or start >= end:
            raise ValueError("invalid partition boundary")
        chunks.append(chapters[start:end])
        end = start
    if end != 0:
        raise ValueError("partition omits chapters")
    return list(reversed(chunks))


def build_chronological_data() -> dict:
    from sitegen.chronological_plan import compress_readings, load_sequence, validate_plan

    stream = load_sequence(load_chapters())
    chunks = partition_uniform(reading_units(stream))
    data = {"days": [
        {"readings": compress_readings([chapter for unit in chunk for chapter in unit.chapters]),
         "seconds": sum(unit.tenths for unit in chunk) / 10}
        for chunk in chunks
    ]}
    validate_plan(data, stream)
    return data


def durations(chunks: list[list]) -> list[int]:
    return [sum(item.tenths for item in chunk) for chunk in chunks]


def score(first: list[list], second: list[list], total: int) -> tuple[int, int]:
    """Compare whole-day deviations in integer tenths, scaled by the day count."""
    days = len(first)
    deviations = [abs((a + b) * days - total) for a, b in zip(durations(first), durations(second), strict=True)]
    return max(deviations), sum(value * value for value in deviations)


def partition(chapters: list, days: int = 365, *, offsets: list[int] | None = None, target_total: int | None = None) -> list[list]:
    """Exact linear partition with a different target for each day; max deviation, then squared error."""
    count = len(chapters)
    if count < days:
        raise ValueError("not enough chapters for non-empty days")
    if offsets is None:
        offsets = [0] * days
    if len(offsets) != days or any(type(value) is not int or value < 0 for value in offsets):
        raise ValueError("offsets must have one non-negative integer duration per day")
    prefix = [0]
    for item in chapters:
        prefix.append(prefix[-1] + item.tenths)
    total = prefix[-1] + sum(offsets)
    if target_total is not None and target_total != total:
        raise ValueError("target total differs from combined stream duration")
    previous: list[tuple[int, int] | None] = [None] * (count + 1)
    previous[0] = (0, 0)
    parents: list[list[int]] = [[-1] * (count + 1)]
    for day in range(1, days + 1):
        current: list[tuple[int, int] | None] = [None] * (count + 1)
        parent = [-1] * (count + 1)
        offset = offsets[day - 1]
        for end in range(day, count - (days - day) + 1):
            best = None
            best_start = -1
            for start in range(day - 1, end):
                prior = previous[start]
                if prior is None:
                    continue
                deviation = abs((prefix[end] - prefix[start] + offset) * days - total)
                candidate = (max(prior[0], deviation), prior[1] + deviation * deviation)
                if best is None or candidate < best:
                    best, best_start = candidate, start
            current[end] = best
            parent[end] = best_start
        previous = current
        parents.append(parent)
    if previous[count] is None:
        raise ValueError("could not partition chapters")
    result = []
    end = count
    for day in range(days, 0, -1):
        start = parents[day][end]
        if start < 0 or start == end:
            raise ValueError("empty partition chunk")
        result.append(chapters[start:end])
        end = start
    if end != 0:
        raise ValueError("partition omits chapters")
    result.reverse()
    return result


def build_data() -> dict:
    chapters = load_chapters()
    a, b = streams(chapters)
    a_units, b_units = reading_units(a), reading_units(b)
    total = sum(item.tenths for item in chapters)
    chunks_b = partition(b_units)
    chunks_a = partition(a_units, offsets=durations(chunks_b), target_total=total)
    best = score(chunks_a, chunks_b, total)
    for _ in range(MAX_ALTERNATIONS):
        next_b = partition(b_units, offsets=durations(chunks_a), target_total=total)
        next_a = partition(a_units, offsets=durations(next_b), target_total=total)
        next_score = score(next_a, next_b, total)
        if next_score >= best:
            break
        chunks_a, chunks_b, best = next_a, next_b, next_score
    days = []
    for first, second in zip(chunks_a, chunks_b, strict=True):
        tenths = sum(item.tenths for item in first + second)
        first_chapters = [chapter for unit in first for chapter in unit.chapters]
        second_chapters = [chapter for unit in second for chapter in unit.chapters]
        days.append({"a": range_data(first_chapters), "b": range_data(second_chapters), "seconds": tenths / 10})
    data = {"days": days}
    validate_plan(data, chapters)
    return data


def build_sequential_data() -> dict:
    chapters = load_chapters()
    chunks = partition(reading_units(chapters))
    days = []
    for chunk in chunks:
        reading = [chapter for unit in chunk for chapter in unit.chapters]
        days.append({"reading": range_data(reading), "seconds": sum(unit.tenths for unit in chunk) / 10})
    data = {"days": days}
    validate_sequential_plan(data, chapters)
    return data


def main() -> None:
    from sitegen.chronological_plan import PLAN_PATH as CHRONOLOGICAL_PLAN_PATH

    if sys.argv[1:] not in ([], ["--chronological-only"]):
        raise SystemExit("usage: build_reading_plan.py [--chronological-only]")
    chronological = build_chronological_data()
    CHRONOLOGICAL_PLAN_PATH.write_text(json.dumps(chronological, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {CHRONOLOGICAL_PLAN_PATH} (365 days)")
    if sys.argv[1:] == ["--chronological-only"]:
        return
    parallel = build_data()
    sequential = build_sequential_data()
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(parallel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEQUENTIAL_PLAN_PATH.write_text(json.dumps(sequential, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PLAN_PATH} and {SEQUENTIAL_PLAN_PATH} (365 days each)")


if __name__ == "__main__":
    main()
