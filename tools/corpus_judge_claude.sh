#!/usr/bin/env bash
# Internal editorial judge. Claude CLI authentication stays in its runtime environment.
set -euo pipefail
claude -p --model opus --output-format json --tools "" |
  python3 "$(dirname -- "${BASH_SOURCE[0]}")/corpus_judge.py"
