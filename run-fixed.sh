#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <TICKER> [YYYY-MM-DD]" >&2
  echo "Environment overrides: TRADINGAGENTS_ANALYSTS=market,news TRADINGAGENTS_QUICK_MODEL=... TRADINGAGENTS_DEEP_MODEL=... TRADINGAGENTS_DEPTH=5 TRADINGAGENTS_REASONING_EFFORT=high" >&2
  echo "Example: $0 600330.SS" >&2
  echo "Example: $0 600330.SS 2026-05-04" >&2
  exit 2
fi

TICKER="$1"
# 默认使用当前北京时间日期；传入第二个参数时覆盖。
ANALYSIS_DATE="${2:-$(TZ=Asia/Shanghai date +%F)}"
# 这些配置支持两种方式覆盖：
# 1) 写入 .env，由 docker compose env_file 注入容器；
# 2) 运行命令前临时设置同名环境变量，脚本会用 docker compose -e 传入容器。
DOCKER_ENV_ARGS=()
CLI_OVERRIDE_ARGS=()
if [[ -n "${TRADINGAGENTS_DEPTH:-}" ]]; then
  DOCKER_ENV_ARGS+=("-e" "TRADINGAGENTS_DEPTH=$TRADINGAGENTS_DEPTH")
  CLI_OVERRIDE_ARGS+=("--depth" "$TRADINGAGENTS_DEPTH")
fi
if [[ -n "${TRADINGAGENTS_REASONING_EFFORT:-}" ]]; then
  DOCKER_ENV_ARGS+=("-e" "TRADINGAGENTS_REASONING_EFFORT=$TRADINGAGENTS_REASONING_EFFORT")
  CLI_OVERRIDE_ARGS+=("--reasoning-effort" "$TRADINGAGENTS_REASONING_EFFORT")
fi
if [[ -n "${TRADINGAGENTS_ANALYSTS:-}" ]]; then
  DOCKER_ENV_ARGS+=("-e" "TRADINGAGENTS_ANALYSTS=$TRADINGAGENTS_ANALYSTS")
  CLI_OVERRIDE_ARGS+=("--analysts" "$TRADINGAGENTS_ANALYSTS")
fi
if [[ -n "${TRADINGAGENTS_QUICK_MODEL:-}" ]]; then
  DOCKER_ENV_ARGS+=("-e" "TRADINGAGENTS_QUICK_MODEL=$TRADINGAGENTS_QUICK_MODEL")
  CLI_OVERRIDE_ARGS+=("--quick-model" "$TRADINGAGENTS_QUICK_MODEL")
fi
if [[ -n "${TRADINGAGENTS_DEEP_MODEL:-}" ]]; then
  DOCKER_ENV_ARGS+=("-e" "TRADINGAGENTS_DEEP_MODEL=$TRADINGAGENTS_DEEP_MODEL")
  CLI_OVERRIDE_ARGS+=("--deep-model" "$TRADINGAGENTS_DEEP_MODEL")
fi

printf 'TradingAgents runtime overrides: analysts=%s quick_model=%s deep_model=%s depth=%s reasoning_effort=%s\n' \
  "${TRADINGAGENTS_ANALYSTS:-<container/.env default>}" \
  "${TRADINGAGENTS_QUICK_MODEL:-<container/.env default>}" \
  "${TRADINGAGENTS_DEEP_MODEL:-<container/.env default>}" \
  "${TRADINGAGENTS_DEPTH:-<container/.env default>}" \
  "${TRADINGAGENTS_REASONING_EFFORT:-<container/.env default>}" >&2

cd "$(dirname "$0")"

docker compose run --rm "${DOCKER_ENV_ARGS[@]}" tradingagents \
  --ticker "$TICKER" \
  --date "$ANALYSIS_DATE" \
  --llm-provider openai \
  --backend-url http://localhost:3000/v1 \
  --output-language Chinese \
  "${CLI_OVERRIDE_ARGS[@]}"
