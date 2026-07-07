#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3.12}"
VENV_DIR="${VENV:-.venv}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
WHEELHOUSE="${WHEELHOUSE:-$(cd -- "${SOURCE_DIR}/.." && pwd)/wheelhouse}"

cd "${SOURCE_DIR}"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
VENV_PYTHON="${SOURCE_DIR}/${VENV_DIR}/bin/python"

"${VENV_PYTHON}" -m pip install --no-index --find-links "${WHEELHOUSE}" oracle-mcp-server
"${VENV_PYTHON}" -c "import mcp, oracledb, pydantic, dotenv, yaml; print('imports ok')"
"${SOURCE_DIR}/${VENV_DIR}/bin/oracle-mcp-check" --help

echo
echo "Offline install complete."
echo "Python: ${VENV_PYTHON}"
echo "Next: copy profiles.example.yaml to profiles.yaml and .env.example to .env."
