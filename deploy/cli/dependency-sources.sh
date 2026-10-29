#!/usr/bin/env bash

# Image registry selection also selects defaults for Skill dependency downloads.
# Explicit process or .env settings always take precedence.
movo_configure_dependency_sources() {
  if [[ -n "${MOVO_MIRROR:-}" ]]; then
    MOVO_DEPENDENCY_MIRROR="${MOVO_MIRROR}"
    export MOVO_DEPENDENCY_MIRROR
  fi
  [[ "${MOVO_MIRROR:-global}" == cn ]] || return 0

  if [[ -z "${MOVO_PIP_INDEX_URL:-}" && -z "$(dotenv_value MOVO_PIP_INDEX_URL)" ]]; then
    MOVO_PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"
    export MOVO_PIP_INDEX_URL
  fi
  if [[ -z "${MOVO_NPM_REGISTRY:-}" && -z "$(dotenv_value MOVO_NPM_REGISTRY)" ]]; then
    MOVO_NPM_REGISTRY="https://registry.npmmirror.com"
    export MOVO_NPM_REGISTRY
  fi
}
