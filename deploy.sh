#!/bin/bash

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Timing function
start_time=$(date +%s)
section_start_time=0

start_section() {
    section_start_time=$(date +%s)
    echo -e "${BLUE}┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│${NC} ${WHITE}$1${NC}"
    echo -e "${BLUE}└─────────────────────────────────────────────────────────────────┘${NC}"
}

end_section() {
    local end_time=$(date +%s)
    local duration=$((end_time - section_start_time))
    echo -e "${GREEN}✓ Completed in ${duration}s${NC}"
    echo ""
}

# Parse command line arguments
SKIP_TESTS=false
while getopts "s" opt; do
  case $opt in
    s) SKIP_TESTS=true ;;
    \?) echo "Invalid option -$OPTARG" >&2; exit 1 ;;
  esac
done

set -e  # Exit on any error

# Local Preparation
start_section "🔧 Local Preparation"
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    exit 1
fi

source .env
echo "Environment loaded"

ruff check . --fix
ruff format .
echo "Code quality checks completed"

# Run tests if not skipped
if [ "$SKIP_TESTS" = false ]; then
    echo "Running tests..."
    pytest . --maxfail=1 --lf -q

    # If any of the above commands failed, exit
    if [ $? -ne 0 ]; then
        echo -e "${RED}Tests failed! Aborting deployment.${NC}"
        exit 1
    fi
    echo "Tests completed"
else
    echo "Tests skipped"
fi
end_section

# Package Deployment
start_section "📦 Package Deployment"
echo "Creating project directory..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p /data/projects/sender"

echo "Creating Python package archive..."
TEMP_DIR=$(mktemp -d)
if [ -f "$TEMP_DIR/sender.tar.gz" ]; then
    rm "$TEMP_DIR/sender.tar.gz"
fi

# Create clean tar archive without macOS metadata
COPYFILE_DISABLE=1 tar \
    --exclude='venv' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='.pytest_cache' \
    --exclude='node_modules' \
    -czf "$TEMP_DIR/sender.tar.gz" \
    src \
    requirements.txt \
    clients.yaml \
    google-service-account.json \
    .env \
    Dockerfile \
    run.sh \
    sender.logrotate

echo "Copying and extracting Python package..."
scp "$TEMP_DIR/sender.tar.gz" \
    ${REMOTE_USER}@${REMOTE_HOST}:/data/projects/sender/

ssh ${REMOTE_USER}@${REMOTE_HOST} \
    "cd /data/projects/sender && \
     tar xzf sender.tar.gz 2>/dev/null && \
     rm sender.tar.gz"

rm -rf "$TEMP_DIR"
end_section

# Server Configuration
start_section "⚙️ Server Configuration"
echo "Ensuring wrapper permissions..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "chmod +x /data/projects/sender/run.sh"

echo "Building Docker image..."
ssh ${REMOTE_USER}@${REMOTE_HOST} '
    cd /data/projects/sender
    # Stop and remove any existing containers in a single atomic operation
    containers=$(docker ps -aq --filter ancestor=sender)
    if [ ! -z "$containers" ]; then
        docker rm -f $containers
    fi
    # Remove old image
    docker rmi sender || true
    # Build new image
    docker build -t sender -f Dockerfile .
'

echo "Setting up log rotation..."
ssh ${REMOTE_USER}@${REMOTE_HOST} '
    # Copy logrotate configuration
    cp /data/projects/sender/sender.logrotate /etc/logrotate.d/sender

    echo "Log rotation configured for /var/log/sender.log"
    echo "  - Daily rotation"
    echo "  - Keep 30 days of logs"
    echo "  - Compress old logs"
'

echo "Setting up cron jobs..."
ssh ${REMOTE_USER}@${REMOTE_HOST} '
    # Get current crontab without sender jobs and without any existing CRON_TZ lines
    TEMP_CRONTAB=$(crontab -l 2>/dev/null | grep -v "sender" | grep -v -E "^CRON_TZ=" || true)
    CRON_TZ_LINE="CRON_TZ=Europe/Moscow"
    CRON_LINE="0 9-21 * * * bash -lc \"cd /data/projects/sender && ./run.sh\""

    {
        echo "$TEMP_CRONTAB"
        echo "$CRON_TZ_LINE"
        echo "$CRON_LINE"
    } | crontab -
'
end_section

# Calculate total deployment time
end_time=$(date +%s)
total_duration=$((end_time - start_time))
current_time=$(date '+%Y-%m-%d %H:%M:%S')

echo -e "${CYAN}┌─────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${CYAN}│${NC} ${WHITE}🎉 Deployment completed successfully!${NC}"
echo -e "${CYAN}│${NC} ${GREEN}Total deployment time: ${total_duration}s${NC}"
echo -e "${CYAN}│${NC} ${YELLOW}Finished at: ${current_time}${NC}"
echo -e "${CYAN}└─────────────────────────────────────────────────────────────────┘${NC}"


