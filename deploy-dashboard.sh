#!/bin/bash
# Deploy sender dashboard to apps server
# Copies dashboard files and applies Traefik config changes

set -e

source .env

SSH_OPTS="-o ControlMaster=no -o ConnectTimeout=30"

echo "📦 Copying dashboard files..."
ssh $SSH_OPTS ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p /data/projects/sender/dashboard"
scp $SSH_OPTS -r dashboard/* ${REMOTE_USER}@${REMOTE_HOST}:/data/projects/sender/dashboard/

echo "⚙️  Copying Traefik config..."
scp $SSH_OPTS \
    "../../servers/3 - apps/services/traefik/config/sender-dashboard.yml" \
    ${REMOTE_USER}@${REMOTE_HOST}:/data/projects/traefik/config/sender-dashboard.yml

echo "🔄 Restarting Traefik (brief outage for all services)..."
ssh $SSH_OPTS ${REMOTE_USER}@${REMOTE_HOST} '
    cd /data/projects/traefik && \
    docker compose up -d --force-recreate traefik && \
    echo "Traefik restarted"
'

echo "✅ Dashboard deployed! https://sender.l1979.ru"
