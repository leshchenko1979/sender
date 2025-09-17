#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

LOG_FILE=/var/log/sender.log
mkdir -p "$(dirname "$LOG_FILE")" || true

# Ensure image exists (rebuild if pruned)
if ! docker image inspect sender >/dev/null 2>&1; then
  echo "[$(date --iso-8601=seconds)] Image missing. Rebuilding..." | tee -a "$LOG_FILE"
  docker build -t sender -f Dockerfile . >> "$LOG_FILE" 2>&1
  echo "[$(date --iso-8601=seconds)] Rebuild complete." | tee -a "$LOG_FILE"
fi

# Remove any previous container with same name (if left over)
docker rm -f sender >/dev/null 2>&1 || true

echo "[$(date --iso-8601=seconds)] Starting sender run..." | tee -a "$LOG_FILE"
docker run --name sender sender >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "[$(date --iso-8601=seconds)] Run finished with code $EXIT_CODE" | tee -a "$LOG_FILE"
exit $EXIT_CODE


