#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <TICKER> [YYYY-MM-DD]" >&2
  echo "Example: $0 600330.SS" >&2
  echo "Example: $0 600330.SS 2026-05-04" >&2
  exit 2
fi

TICKER="$1"
# 默认使用当前北京时间日期；传入第二个参数时覆盖。
ANALYSIS_DATE="${2:-$(TZ=Asia/Shanghai date +%F)}"

cd "$(dirname "$0")"

docker compose run --rm tradingagents \
  --ticker "$TICKER" \
  --date "$ANALYSIS_DATE" \
  --analysts market,social,news,fundamentals \
  --depth 5 \
  --llm-provider openai \
  --backend-url http://localhost:3000/v1 \
  --quick-model gpt-5.5 \
  --deep-model gpt-5.5 \
  --output-language Chinese \
  --reasoning-effort high
