#!/usr/bin/env bash
# Internal editorial judge. Claude CLI authentication stays in its runtime environment.
set -euo pipefail
judge_protocol="$(dirname -- "${BASH_SOURCE[0]}")/corpus_judge.py"
judge_schema="$(python3 "$judge_protocol" --schema)"
claude -p --model opus --output-format json --tools "" --json-schema "$judge_schema" |
  python3 "$judge_protocol"
