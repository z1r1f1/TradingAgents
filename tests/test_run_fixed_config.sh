#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$DOCKER_ARGS_LOG"
EOF
chmod +x "$TMP_DIR/docker"

run_and_capture() {
  DOCKER_ARGS_LOG="$TMP_DIR/docker-args.log" PATH="$TMP_DIR:$PATH" "$PROJECT_DIR/run-fixed.sh" "$@" >/dev/null
  tr '\n' ' ' < "$TMP_DIR/docker-args.log"
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "Expected docker args to contain: $needle" >&2
    echo "Actual args: $haystack" >&2
    exit 1
  fi
}

DEFAULT_ARGS="$(run_and_capture 600330.SS 2000-01-01)"
assert_contains "$DEFAULT_ARGS" "tradingagents --ticker 600330.SS"
if [[ "$DEFAULT_ARGS" == *"--depth"* || "$DEFAULT_ARGS" == *"--reasoning-effort"* ]]; then
  echo "run-fixed.sh should let CLI/.env defaults provide depth and reasoning effort" >&2
  echo "Actual args: $DEFAULT_ARGS" >&2
  exit 1
fi
if [[ "$DEFAULT_ARGS" == *"--analysts"* || "$DEFAULT_ARGS" == *"--quick-model"* || "$DEFAULT_ARGS" == *"--deep-model"* ]]; then
  echo "run-fixed.sh should let CLI/.env defaults provide analysts and models unless host overrides are set" >&2
  echo "Actual args: $DEFAULT_ARGS" >&2
  exit 1
fi

OVERRIDE_ARGS="$({ \
  TRADINGAGENTS_DEPTH=3 \
  TRADINGAGENTS_REASONING_EFFORT=medium \
  TRADINGAGENTS_ANALYSTS=market,news \
  TRADINGAGENTS_QUICK_MODEL=gpt-5.5-mini \
  TRADINGAGENTS_DEEP_MODEL=gpt-5.5 \
  run_and_capture 600330.SS 2000-01-01; \
})"
assert_contains "$OVERRIDE_ARGS" "-e TRADINGAGENTS_DEPTH=3"
assert_contains "$OVERRIDE_ARGS" "-e TRADINGAGENTS_REASONING_EFFORT=medium"
assert_contains "$OVERRIDE_ARGS" "-e TRADINGAGENTS_ANALYSTS=market,news"
assert_contains "$OVERRIDE_ARGS" "-e TRADINGAGENTS_QUICK_MODEL=gpt-5.5-mini"
assert_contains "$OVERRIDE_ARGS" "-e TRADINGAGENTS_DEEP_MODEL=gpt-5.5"
assert_contains "$OVERRIDE_ARGS" "tradingagents --ticker 600330.SS"
assert_contains "$OVERRIDE_ARGS" "--analysts market,news"
assert_contains "$OVERRIDE_ARGS" "--quick-model gpt-5.5-mini"
assert_contains "$OVERRIDE_ARGS" "--deep-model gpt-5.5"
assert_contains "$OVERRIDE_ARGS" "--depth 3"
assert_contains "$OVERRIDE_ARGS" "--reasoning-effort medium"
