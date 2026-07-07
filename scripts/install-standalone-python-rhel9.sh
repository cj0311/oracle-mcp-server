#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PYTHONHOME:-}" || -n "${PYTHONPATH:-}" ]]; then
  echo "Ignoring PYTHONHOME/PYTHONPATH while bootstrapping standalone Python." >&2
  unset PYTHONHOME
  unset PYTHONPATH
fi
export PYTHONNOUSERSITE=1

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE="${1:-${SCRIPT_DIR}/cpython-3.12.10+20250529-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz}"
PREFIX="${PREFIX:-${HOME}/.local/python-3.12.10}"
TARGET_NAME="$(basename -- "${PREFIX}")"

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "Python archive not found: ${ARCHIVE}" >&2
  exit 1
fi

if [[ "${TARGET_NAME}" != python-* ]]; then
  echo "Install prefix must end with a python-* directory: ${PREFIX}" >&2
  echo "Example: PREFIX=/opt/python-3.12.10" >&2
  exit 1
fi

if [[ -e "${PREFIX}" && -n "$(find "${PREFIX}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" && "${FORCE:-0}" != "1" ]]; then
  echo "Install prefix is not empty: ${PREFIX}" >&2
  echo "Set FORCE=1 to replace it, or choose another PREFIX." >&2
  exit 1
fi

if [[ "${FORCE:-0}" == "1" && -e "${PREFIX}" ]]; then
  rm -rf -- "${PREFIX}"
fi

mkdir -p -- "${PREFIX}"
tar -xzf "${ARCHIVE}" -C "${PREFIX}" --strip-components=1

if [[ ! -f "${PREFIX}/lib/python3.12/encodings/__init__.py" ]]; then
  echo "Python stdlib was not extracted correctly: ${PREFIX}/lib/python3.12/encodings/__init__.py" >&2
  exit 1
fi

"${PREFIX}/bin/python3.12" --version
"${PREFIX}/bin/python3.12" -m pip --version

echo
echo "Python 3.12 install complete."
echo "Python: ${PREFIX}/bin/python3.12"
echo "To use it in the current shell:"
echo "  export PATH=\"${PREFIX}/bin:\$PATH\""
