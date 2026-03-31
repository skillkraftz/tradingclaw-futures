#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PORT_OVERRIDE=""
PROVIDER_OVERRIDE=""
SKIP_TESTS=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./start_tradingclaw.sh [--skip-tests] [--port PORT] [--provider file|twelvedata] [--dry-run]

Options:
  --skip-tests           Skip pytest before starting the API.
  --port PORT            Override TRADINGCLAW_PORT for this run.
  --provider PROVIDER    Set TRADINGCLAW_DEFAULT_PROVIDER for this run.
  --dry-run              Validate setup and exit before starting the API.
  --help                 Show this help text.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --port)
      PORT_OVERRIDE="${2:-}"
      shift 2
      ;;
    --provider)
      PROVIDER_OVERRIDE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name" >&2
    exit 1
  fi
}

require_command python3

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  echo "Missing ${ROOT_DIR}/.env. Copy .env.example and fill in the required values." >&2
  exit 1
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "Installing TradingClaw in editable mode"
python -m pip install -e '.[dev]'

set -a
# shellcheck disable=SC1090
source "${ROOT_DIR}/.env"
set +a

if [[ -n "${PORT_OVERRIDE}" ]]; then
  export TRADINGCLAW_PORT="${PORT_OVERRIDE}"
fi
if [[ -n "${PROVIDER_OVERRIDE}" ]]; then
  if [[ "${PROVIDER_OVERRIDE}" != "file" && "${PROVIDER_OVERRIDE}" != "twelvedata" ]]; then
    echo "Unsupported provider override: ${PROVIDER_OVERRIDE}" >&2
    exit 1
  fi
  export TRADINGCLAW_DEFAULT_PROVIDER="${PROVIDER_OVERRIDE}"
fi

: "${TRADINGCLAW_HOST:=127.0.0.1}"
: "${TRADINGCLAW_PORT:=8787}"
: "${TRADINGCLAW_DEFAULT_PROVIDER:=file}"
: "${TRADINGCLAW_DB_PATH:=./data/runtime/tradingclaw.sqlite3}"
: "${TRADINGCLAW_OPENCLAW_ENABLED:=false}"

if ! [[ "${TRADINGCLAW_PORT}" =~ ^[0-9]+$ ]]; then
  echo "TRADINGCLAW_PORT must be numeric. Got: ${TRADINGCLAW_PORT}" >&2
  exit 1
fi

if [[ "${TRADINGCLAW_DEFAULT_PROVIDER}" != "file" && "${TRADINGCLAW_DEFAULT_PROVIDER}" != "twelvedata" ]]; then
  echo "TRADINGCLAW_DEFAULT_PROVIDER must be 'file' or 'twelvedata'. Got: ${TRADINGCLAW_DEFAULT_PROVIDER}" >&2
  exit 1
fi

if [[ "${TRADINGCLAW_DEFAULT_PROVIDER}" == "twelvedata" && -z "${TRADINGCLAW_TWELVEDATA_API_KEY:-}" ]]; then
  echo "TRADINGCLAW_TWELVEDATA_API_KEY is required when --provider twelvedata is used." >&2
  exit 1
fi

echo "TradingClaw diagnostics"
echo "  Host: ${TRADINGCLAW_HOST}"
echo "  Port: ${TRADINGCLAW_PORT}"
echo "  Provider: ${TRADINGCLAW_DEFAULT_PROVIDER}"
echo "  DB path: ${TRADINGCLAW_DB_PATH}"
echo "  OpenClaw enabled: ${TRADINGCLAW_OPENCLAW_ENABLED}"

if [[ "${SKIP_TESTS}" -eq 0 ]]; then
  echo "Running test suite"
  python -m pytest -q
else
  echo "Skipping tests"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Dry run complete. TradingClaw was not started."
  exit 0
fi

echo "Starting TradingClaw API server"
exec python -m openclaw_futures.cli serve
