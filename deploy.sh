#!/bin/bash

# Parse command line arguments
SKIP_TESTS=false
while getopts "s" opt; do
  case $opt in
    s) SKIP_TESTS=true ;;
    \?) echo "Invalid option -$OPTARG" >&2; exit 1 ;;
  esac
done

set -e  # Exit on any error

# Load environment variables
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    exit 1
fi

source .env

echo "Running code quality checks..."

# Run isort to sort imports
echo "Running isort..."
isort .

# Run black for code formatting
echo "Running black..."
black .

# Run tests if not skipped
if [ "$SKIP_TESTS" = false ]; then
    echo "Running tests..."
    pytest . -v

    # If any of the above commands failed, exit
    if [ $? -ne 0 ]; then
        echo "Tests failed! Aborting deployment."
        exit 1
    fi
else
    echo "Skipping tests..."
fi

# Create project directory
echo "Creating project directory..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p /data/projects/sender"

# Create package archive
echo "Creating Python package archive..."
TEMP_DIR=$(mktemp -d)
if [ -f "$TEMP_DIR/sender.tar.gz" ]; then
    rm "$TEMP_DIR/sender.tar.gz"
fi

tar \
    --exclude='venv' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='.pytest_cache' \
    --exclude='node_modules' \
    -czf "$TEMP_DIR/sender.tar.gz" \
    src \
    pyproject.toml \
    README.md \
    clients.yaml \
    google-service-account.json \
    .env \
    Dockerfile \
    run.sh \
    sender.logrotate

# Copy and extract Python package
echo "Copying and extracting Python package..."
scp "$TEMP_DIR/sender.tar.gz" \
    ${REMOTE_USER}@${REMOTE_HOST}:/data/projects/sender/

ssh ${REMOTE_USER}@${REMOTE_HOST} \
    "cd /data/projects/sender && \
     tar xzf sender.tar.gz && \
     rm sender.tar.gz"

rm -rf "$TEMP_DIR"

# Ensure wrapper is executable on VDS
echo "Ensuring wrapper permissions..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "chmod +x /data/projects/sender/run.sh"

# Build Docker image
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

# Set up log rotation
echo "Setting up log rotation..."
ssh ${REMOTE_USER}@${REMOTE_HOST} '
    # Copy logrotate configuration
    cp /data/projects/sender/sender.logrotate /etc/logrotate.d/sender
    
    # Test logrotate configuration
    logrotate -d /etc/logrotate.d/sender
    
    echo "Log rotation configured for /var/log/sender.log"
    echo "  - Daily rotation"
    echo "  - Keep 30 days of logs"
    echo "  - Compress old logs"
'

# Set up cron jobs
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

echo "Deployment completed successfully!"


