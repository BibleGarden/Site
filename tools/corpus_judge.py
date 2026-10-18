"""Strict editorial judge protocol and Claude CLI envelope decoding (stdlib only)."""

import json
import sys


class CheckError(Exception):
    pass


PASS_CATEGORIES = {"supported", "secondary_omission"}
FAIL_CATEGORIES = {"distortion", "addition", "contradiction", "misattribution",
                   "meaning_changing_omission", "close_paraphrase"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            # Keys may contain private model text; do not include them in errors.
            raise CheckError("Duplicate JSON object key in judge response")
        result[key] = value
    return result


def assessment_verdict(assessment):
    if (not isinstance(assessment, dict) or set(assessment) != {"category", "reason"}
            or not isinstance(assessment["category"], str)
            or assessment["category"] not in PASS_CATEGORIES | FAIL_CATEGORIES
            or not isinstance(assessment["reason"], str) or not assessment["reason"].strip()):
        raise CheckError("LLM assessment must contain a known category and non-empty reason:string")
    return {"verdict": "PASS" if assessment["category"] in PASS_CATEGORIES else "FAIL", **assessment}


def validate_verdict(verdict):
    if not isinstance(verdict, dict) or set(verdict) != {"verdict", "category", "reason"}:
        raise CheckError("LLM judge must return verdict, category and reason")
    expected = assessment_verdict({key: verdict[key] for key in ("category", "reason")})
    if verdict != expected:
        raise CheckError("LLM verdict contradicts its category")
    return expected


def claude_verdict(envelope):
    if not isinstance(envelope, dict) or envelope.get("is_error") is True:
        raise CheckError("Claude returned an error envelope")
    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise CheckError("Claude response is missing result text")
    # Decode the first object, never skip a malformed candidate to find a later one.
    # Formatting prose/fences may surround it; a second object/array is ambiguous.
    start = result.find("{")
    if start < 0 or "[" in result[:start]:
        raise CheckError("Claude response must contain exactly one JSON object")
    try:
        assessment, end = json.JSONDecoder(object_pairs_hook=unique_object).raw_decode(result, start)
    except ValueError as exc:
        raise CheckError("Claude assessment contains malformed JSON") from exc
    if any(char in result[end:] for char in "{}[]"):
        raise CheckError("Claude response contains ambiguous extra JSON")
    return assessment_verdict(assessment)


def main():
    try:
        envelope = json.load(sys.stdin, object_pairs_hook=unique_object)
        verdict = claude_verdict(envelope)
    except (CheckError, ValueError) as exc:
        # Never echo the raw model text or CLI envelope into diagnostics.
        sys.exit(str(exc))
    json.dump(verdict, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
