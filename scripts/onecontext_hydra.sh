#!/usr/bin/env bash
set -euo pipefail

# Project-local OneContext bootstrap for jsr-hydra.
# Usage:
#   source scripts/onecontext_hydra.sh

PROJECT_ROOT="/Users/thuanle/Documents/JSR/JSRAlgoMac/jsr-hydra"
HYDRA_AGENT_ID="bfec591c-8350-4837-8ef3-ff2d0210a5fc"

if ! command -v onecontext >/dev/null 2>&1; then
  echo "onecontext command not found. Install first."
  return 1 2>/dev/null || exit 1
fi

cd "${PROJECT_ROOT}"
export ALINE_AGENT_ID="${HYDRA_AGENT_ID}"

echo "ALINE_AGENT_ID=${ALINE_AGENT_ID}"
echo "Project: ${PROJECT_ROOT}"
echo
echo "Context snapshot:"
onecontext context show

