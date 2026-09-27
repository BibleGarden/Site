"""Build the deterministic 365-day Bible reading plan from chapter audio lengths."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sitegen.reading_plan import (  # noqa: E402
    PLAN_PATH, SEQUENTIAL_PLAN_PATH, load_chapters, range_data, reading_units,
    streams, validate_plan, validate_sequential_plan,
)


MAX_ALTERNATIONS = 8


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
    parallel = build_data()
    sequential = build_sequential_data()
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(parallel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEQUENTIAL_PLAN_PATH.write_text(json.dumps(sequential, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PLAN_PATH} and {SEQUENTIAL_PLAN_PATH} (365 days each)")


if __name__ == "__main__":
    main()
