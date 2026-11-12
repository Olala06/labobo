#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)'
"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" -m genomic_detective --version
"$PYTHON" -m genomic_detective prepare
