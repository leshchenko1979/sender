#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"/..

# Ensure image exists
if ! docker image inspect forwarder:latest &>/dev/null; then
  echo "Building forwarder:latest..."
  docker build -t forwarder:latest -f Dockerfile.forwarder .
fi

exec docker run --rm \
  --network=traefik-public \
  -e BRIDGE_URL=http://fast-mcp-telegram:8000 \
  -e BEARER_TOKEN=a0wLhmcdwQI7HJpQNUSXak5Oqp20CDFwWXU6awNrHK0 \
  -e TARGET_USER=leshchenko1979 \
  -e STATE_FILE=/data/state.json \
  -v forwarder-state:/data \
  forwarder:latest
