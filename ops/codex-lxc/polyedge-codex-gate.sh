#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="/opt/stacks/polyedge-v2"
readonly HELPER_BIN="/usr/local/bin/polyedge-codex-compose"
readonly GIT_BIN="/usr/bin/git"
readonly SUDO_BIN="/usr/bin/sudo"
readonly MAX_LOG_TAIL=5000
readonly -a ALLOWED_SERVICES=(
  "analysis"
  "trading"
  "dashboard"
  "weather"
  "trading-weather"
  "core-debug"
)
readonly -a SAFE_UPDATE_SERVICES=(
  "analysis"
  "trading"
  "dashboard"
  "weather"
  "trading-weather"
)

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

contains() {
  local needle="$1"
  shift

  local item
  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done

  return 1
}

validate_service() {
  local service="$1"
  contains "$service" "${ALLOWED_SERVICES[@]}" || die "service '$service' is not allowed"
}

validate_services() {
  (($# >= 1)) || die "at least one service is required"

  local service
  for service in "$@"; do
    validate_service "$service"
  done
}

require_zero_args() {
  (($# == 0)) || die "unexpected arguments"
}

[[ -x "$GIT_BIN" ]] || die "git binary not found at $GIT_BIN"
[[ -x "$SUDO_BIN" ]] || die "sudo binary not found at $SUDO_BIN"
[[ -x "$HELPER_BIN" ]] || die "helper binary not found at $HELPER_BIN"
[[ -d "$REPO_ROOT" ]] || die "repo root not found at $REPO_ROOT"

raw_command="${SSH_ORIGINAL_COMMAND:-}"
[[ -n "$raw_command" ]] || die "interactive shell access is disabled"
[[ "$raw_command" != *$'\n'* ]] || die "multiline commands are not allowed"
[[ "$raw_command" =~ ^[[:alnum:][:space:]_.-]+$ ]] || die "command contains unsupported characters"

read -r -a argv <<<"$raw_command"
((${#argv[@]} >= 1)) || die "command is required"

command_name="${argv[0]}"
args=("${argv[@]:1}")

case "$command_name" in
  status)
    require_zero_args "${args[@]}"
    "$GIT_BIN" -C "$REPO_ROOT" rev-parse --short HEAD
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" status
    ;;
  git-pull)
    require_zero_args "${args[@]}"
    exec "$GIT_BIN" -C "$REPO_ROOT" pull --ff-only
    ;;
  build)
    validate_services "${args[@]}"
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" build "${args[@]}"
    ;;
  up)
    validate_services "${args[@]}"
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" up "${args[@]}"
    ;;
  down)
    validate_services "${args[@]}"
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" stop "${args[@]}"
    ;;
  restart)
    validate_services "${args[@]}"
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" restart "${args[@]}"
    ;;
  logs)
    ((${#args[@]} >= 1 && ${#args[@]} <= 2)) || die "logs requires a service and optional tail count"
    validate_service "${args[0]}"
    if ((${#args[@]} == 2)); then
      [[ "${args[1]}" =~ ^[0-9]+$ ]] || die "tail count must be a positive integer"
      ((${args[1]} >= 1 && ${args[1]} <= MAX_LOG_TAIL)) || die "tail count must be between 1 and $MAX_LOG_TAIL"
    fi
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" logs "${args[@]}"
    ;;
  safe-update)
    require_zero_args "${args[@]}"
    "$GIT_BIN" -C "$REPO_ROOT" pull --ff-only
    "$SUDO_BIN" --non-interactive "$HELPER_BIN" build "${SAFE_UPDATE_SERVICES[@]}"
    exec "$SUDO_BIN" --non-interactive "$HELPER_BIN" up "${SAFE_UPDATE_SERVICES[@]}"
    ;;
  *)
    die "unsupported command '$command_name'"
    ;;
esac
