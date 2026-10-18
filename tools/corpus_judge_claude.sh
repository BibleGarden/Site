#!/usr/bin/env bash
# Internal editorial judge. Claude CLI authentication stays in its runtime environment.
set -euo pipefail
claude -p --model opus --output-format json --tools "" | python3 -c '
import json
import re
import sys

try:
    envelope = json.load(sys.stdin)
    if envelope.get("is_error") is True:
        raise ValueError("Claude returned an error")
    result = envelope["result"]
    if not isinstance(result, str) or not result.strip():
        raise ValueError("Missing Claude result")
    result = result.strip()
    if result.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", result, re.DOTALL)
        if not match:
            raise ValueError("Malformed JSON fence")
        result = match.group(1)
    verdict = json.loads(result)
except (ValueError, KeyError, TypeError, AttributeError):
    sys.exit("Claude judge returned an invalid response")
json.dump(verdict, sys.stdout, ensure_ascii=False)
'
