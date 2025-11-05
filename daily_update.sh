#!/bin/bash

################################################################################
# Hummingbot Daily Update Script
#
# Purpose: Pull latest code, rebuild Docker image, and restart services
# Schedule: Runs daily at 6 AM via cron
#
# Usage: ./daily_update.sh [--force] [--skip-backup]
#   --force: Force rebuild even if no changes detected
#   --skip-backup: Skip database backup step
################################################################################

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/daily_update_$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="${SCRIPT_DIR}/backups"
FORCE_REBUILD=false
SKIP_BACKUP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_REBUILD=true
            shift
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--force] [--skip-backup]"
            exit 1
            ;;
    esac
done

# Create directories if they don't exist
mkdir -p "${LOG_DIR}" "${BACKUP_DIR}"

# Logging function
log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

# Error handling
error_exit() {
    log "ERROR" "$1"

    # Send notification (if configured)
    if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
        curl -X POST "${DISCORD_WEBHOOK_URL}" \
            -H "Content-Type: application/json" \
            -d "{\"content\": \"❌ Hummingbot update failed: $1\"}" \
            2>/dev/null || true
    fi

    exit 1
}

# Success notification
send_success_notification() {
    log "INFO" "Update completed successfully"

    if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
        curl -X POST "${DISCORD_WEBHOOK_URL}" \
            -H "Content-Type: application/json" \
            -d "{\"content\": \"✅ Hummingbot updated successfully at $(date)\"}" \
            2>/dev/null || true
    fi
}

# Backup function
backup_data() {
    if [[ "${SKIP_BACKUP}" == true ]]; then
        log "INFO" "Skipping backup (--skip-backup flag set)"
        return 0
    fi

    log "INFO" "Creating backup..."
    local backup_file="${BACKUP_DIR}/backup_$(date +%Y%m%d_%H%M%S).tar.gz"

    # Backup critical data (configurations, logs, database)
    tar -czf "${backup_file}" \
        -C "${SCRIPT_DIR}" \
        conf/ \
        data/ \
        logs/ \
        .env \
        2>/dev/null || log "WARN" "Some backup files missing, continuing..."

    log "INFO" "Backup created: ${backup_file}"

    # Keep only last 7 days of backups
    find "${BACKUP_DIR}" -name "backup_*.tar.gz" -mtime +7 -delete
    log "INFO" "Old backups cleaned up (>7 days)"
}

# Main update process
main() {
    log "INFO" "==================== Starting Daily Update ===================="
    log "INFO" "Script directory: ${SCRIPT_DIR}"

    cd "${SCRIPT_DIR}"

    # Step 1: Check if git repo exists
    if [[ ! -d .git ]]; then
        log "WARN" "Not a git repository, skipping git pull"
    else
        log "INFO" "Pulling latest changes from git..."

        # Stash any local changes
        git stash push -m "Auto-stash before daily update $(date)" || true

        # Pull latest changes
        git fetch origin
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)

        if [[ "${LOCAL}" != "${REMOTE}" ]]; then
            log "INFO" "New changes detected, pulling..."
            git pull origin main 2>/dev/null || git pull origin master || error_exit "Git pull failed"
            log "INFO" "Git pull completed"
        else
            log "INFO" "Already up to date"
            if [[ "${FORCE_REBUILD}" != true ]]; then
                log "INFO" "No rebuild needed (use --force to rebuild anyway)"
                exit 0
            fi
        fi
    fi

    # Step 2: Backup existing data
    backup_data

    # Step 3: Check if containers are running
    log "INFO" "Checking running containers..."
    docker-compose ps

    # Step 4: Stop running containers gracefully
    log "INFO" "Stopping Hummingbot containers..."
    docker-compose down --timeout 60 || error_exit "Failed to stop containers"
    log "INFO" "Containers stopped"

    # Step 5: Pull latest Hummingbot base image
    log "INFO" "Pulling latest hummingbot/hummingbot image..."
    docker pull hummingbot/hummingbot:latest || error_exit "Failed to pull base image"
    log "INFO" "Base image updated"

    # Step 6: Rebuild custom image
    log "INFO" "Building custom Hummingbot image..."
    docker-compose build --no-cache --pull || error_exit "Docker build failed"
    log "INFO" "Build completed"

    # Step 7: Clean up old images to save space
    log "INFO" "Cleaning up unused Docker images..."
    docker image prune -f --filter "until=24h"

    # Step 8: Start containers
    log "INFO" "Starting Hummingbot containers..."
    docker-compose up -d || error_exit "Failed to start containers"
    log "INFO" "Containers started"

    # Step 9: Wait for health check
    log "INFO" "Waiting for Hummingbot to become healthy..."
    for i in {1..30}; do
        if docker-compose ps | grep -q "healthy"; then
            log "INFO" "Hummingbot is healthy"
            break
        fi
        sleep 2
    done

    # Step 10: Display status
    log "INFO" "Current container status:"
    docker-compose ps

    # Step 11: Check logs for errors
    log "INFO" "Checking recent logs for errors..."
    docker-compose logs --tail=50 | grep -i error || log "INFO" "No errors found in recent logs"

    # Success
    send_success_notification
    log "INFO" "==================== Update Completed Successfully ===================="
}

# Run main function
main "$@"
