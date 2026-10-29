#!/usr/bin/env bash

# Read a value from the deployment .env without exporting or evaluating it.
# CLI modules are sourced before commands run, so this helper must be loaded
# before any module that derives defaults from .env.
dotenv_value() {
  local key="$1"
  local env_file="${ROOT_DIR}/.env"
  local line=""
  if [[ -f "${env_file}" ]]; then
    line="$(grep -E "^[[:space:]]*${key}=" "${env_file}" | tail -n 1 || true)"
  fi
  line="${line#*=}"
  line="${line%$'\r'}"
  line="${line#\"}"
  line="${line%\"}"
  line="${line#\'}"
  line="${line%\'}"
  printf '%s' "${line}"
}
