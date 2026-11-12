#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "Python 3.10+ is required. Install it from https://www.python.org/downloads/." >&2
  exit 1
fi

"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "Python 3.10+ is required." >&2
  exit 1
}
exec "$PYTHON" -m genomic_detective serve --open "$@"
