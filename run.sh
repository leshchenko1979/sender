#!/bin/bash
set -uo pipefail

cd "$(dirname "$0")"

# Load environment variables
# shellcheck source=/dev/null
[ -f .env ] && source .env

LOG_FILE=/var/log/sender.log
mkdir -p "$(dirname "$LOG_FILE")" || true

# Gatus reporting
GATUS_URL="https://gatus.l1979.ru/api/v1/endpoints/messaging_sender/external"

report_to_gatus() {
  local success=$1
  local error_msg=${2:-}
  local params="success=$success"
  if [ -n "$error_msg" ]; then
    params="$params&error=$(echo "$error_msg" | sed 's/ /+/g')"
  fi
  curl -s -X POST "${GATUS_URL}?${params}" \
    -H "Authorization: Bearer ${GATUS_TOKEN}" \
    --max-time 10 \
    || echo "Gatus update failed"
}

# Ensure image exists (rebuild if pruned)
if ! docker image inspect sender >/dev/null 2>&1; then
  echo "[$(date --iso-8601=seconds)] Image missing. Rebuilding..." | tee -a "$LOG_FILE"
  docker build -t sender -f Dockerfile . >> "$LOG_FILE" 2>&1
  echo "[$(date --iso-8601=seconds)] Rebuild complete." | tee -a "$LOG_FILE"
fi

# Remove any previous container with same name (if left over)
docker rm -f sender >/dev/null 2>&1 || true

echo "[$(date --iso-8601=seconds)] Starting sender run..." | tee -a "$LOG_FILE"
docker run --name sender --cpus=0.5 --memory=256m --memory-reservation=128m sender >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "[$(date --iso-8601=seconds)] Run finished with code $EXIT_CODE" | tee -a "$LOG_FILE"

if [ $EXIT_CODE -eq 0 ]; then
  report_to_gatus "true"
else
  report_to_gatus "false" "exit_code_$EXIT_CODE"
fi

exit $EXIT_CODE
