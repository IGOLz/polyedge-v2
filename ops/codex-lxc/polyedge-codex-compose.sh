#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="/opt/stacks/polyedge-v2"
readonly COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
readonly DOCKER_BIN="/usr/bin/docker"
readonly MAX_LOG_TAIL=5000
readonly -a ALLOWED_SERVICES=(
  "analysis"
  "trading"
  "dashboard"
  "weather"
  "trading-weather"
  "wallet-tracker"
  "core-debug"
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

run_compose() {
  cd "$REPO_ROOT"
  exec "$DOCKER_BIN" compose --project-directory "$REPO_ROOT" -f "$COMPOSE_FILE" "$@"
}

[[ -x "$DOCKER_BIN" ]] || die "docker binary not found at $DOCKER_BIN"
[[ -f "$COMPOSE_FILE" ]] || die "docker compose file not found at $COMPOSE_FILE"
(($# >= 1)) || die "action is required"

action="$1"
shift

case "$action" in
  status)
    (($# == 0)) || die "status does not accept arguments"
    run_compose ps
    ;;
  build)
    validate_services "$@"
    run_compose build "$@"
    ;;
  up)
    validate_services "$@"
    run_compose up -d "$@"
    ;;
  stop)
    validate_services "$@"
    run_compose stop "$@"
    ;;
  restart)
    validate_services "$@"
    run_compose restart "$@"
    ;;
  logs)
    (($# >= 1 && $# <= 2)) || die "logs requires a service and optional tail count"
    service="$1"
    tail_lines="${2:-200}"
    validate_service "$service"
    [[ "$tail_lines" =~ ^[0-9]+$ ]] || die "tail count must be a positive integer"
    ((tail_lines >= 1 && tail_lines <= MAX_LOG_TAIL)) || die "tail count must be between 1 and $MAX_LOG_TAIL"
    run_compose logs --tail "$tail_lines" "$service"
    ;;
  *)
    die "unsupported helper action '$action'"
    ;;
esac
