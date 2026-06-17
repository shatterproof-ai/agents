#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${SHATTER_AGENTS_REPO_OWNER:-shatterproof-ai}"
REPO_NAME="${SHATTER_AGENTS_REPO_NAME:-shatter-agents}"
REPO_REF="${SHATTER_AGENTS_REF:-main}"
SOURCE="${SHATTER_AGENTS_SOURCE:-}"

# Populated only when we download into a temp directory; the script-level EXIT
# trap below removes it. Keeping this global (rather than a function-local) is
# what makes cleanup reliable: the trap is evaluated at exit, by which point a
# local from download_source would already be out of scope.
DOWNLOAD_TMPDIR=""

cleanup() {
  if [[ -n "$DOWNLOAD_TMPDIR" ]]; then
    rm -rf "$DOWNLOAD_TMPDIR"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Install Shatterproof Codex plugins into a local Codex marketplace.

Usage:
  curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter-agents/main/install/codex-home.sh | bash
  curl -fsSL https://raw.githubusercontent.com/shatterproof-ai/shatter-agents/main/install/codex-home.sh | bash -s -- [install-codex-plugins options]

Environment:
  SHATTER_AGENTS_REF=<ref>       GitHub ref to download, default: main
  SHATTER_AGENTS_SOURCE=<path>   Existing checkout to install from, skips download
  CODEX_HOME=<path>              Codex home passed through to the installer
  CODEX=<path>                   Codex executable passed through to the installer

Options are forwarded to scripts/install-codex-plugins.
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "install/codex-home.sh: missing required command: $1" >&2
    exit 1
  fi
}

download_source() {
  require_command curl
  require_command tar

  DOWNLOAD_TMPDIR="$(mktemp -d)"

  local archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${REPO_REF}.tar.gz"
  if [[ "$REPO_REF" == refs/* ]]; then
    archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/${REPO_REF}.tar.gz"
  fi

  echo "[shatterproof-install:codex] downloading ${REPO_OWNER}/${REPO_NAME}@${REPO_REF}" >&2
  curl -fsSL "$archive_url" | tar -xz --strip-components=1 -C "$DOWNLOAD_TMPDIR"
  SOURCE="$DOWNLOAD_TMPDIR"
}

if [[ -z "$SOURCE" ]]; then
  download_source
else
  SOURCE="$(cd "$SOURCE" && pwd)"
fi

# Run the installer as a child process rather than exec'ing it: exec would
# replace this shell, so the EXIT trap (and thus tmpdir cleanup) would never
# run when SOURCE is a downloaded temp directory. Propagate the installer's
# exit status; the trap fires on the way out.
"$SOURCE/scripts/install-codex-plugins" --source "$SOURCE" "$@"
