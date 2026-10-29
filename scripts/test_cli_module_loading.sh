#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

output_file="$(mktemp)"
trap 'rm -f "${output_file}"' EXIT

set +e
env \
  -u COMPOSE_PROFILES \
  -u MOVO_SANDBOX_MANAGER_URL \
  -u MOVO_SANDBOX_SCRIPT_IMAGE \
  -u MOVO_PIP_INDEX_URL \
  -u MOVO_NPM_REGISTRY \
  bash ./movo __module_loading_probe__ >"${output_file}" 2>&1
status=$?
set -e

if [[ "${status}" -ne 2 ]]; then
  cat "${output_file}" >&2
  printf 'Expected unknown-command exit code 2, got %s.\n' "${status}" >&2
  exit 1
fi
if grep -Eq 'command not found|unbound variable' "${output_file}"; then
  cat "${output_file}" >&2
  printf 'CLI module initialization failed before command dispatch.\n' >&2
  exit 1
fi

printf 'CLI modules load successfully with an empty environment.\n'
