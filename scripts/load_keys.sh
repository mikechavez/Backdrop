#!/usr/bin/env bash
set -euo pipefail

load_key() {
  local name="$1"
  local value
  value="$(security find-generic-password -s "$name" -w 2>/dev/null || true)"

  if [ -n "$value" ]; then
    export "$name=$value"
  fi
}

load_key "OPENROUTER_API_KEY"
load_key "GEMINI_API_KEY"
load_key "DEEPSEEK_API_KEY"
load_key "QWEN_API_KEY"
load_key "ANTHROPIC_API_KEY"

export DEEPSEEK_DEFAULT_MODEL="${DEEPSEEK_DEFAULT_MODEL:-deepseek-v4-flash}"