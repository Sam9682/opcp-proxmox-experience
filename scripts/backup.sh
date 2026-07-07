#!/bin/bash
# opcp-proxmox-experience Backup Script

source ./conf/deploy.ini

BACKUP_DIR="backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE"

mkdir -p "$BACKUP_DIR"

echo "Creating backup: $BACKUP_FILE"

# Backup application data volume
containers=$(docker ps -q --filter "name=${NAME_OF_APPLICATION}-.*-${USER_ID:-0}-.*")
if [[ -n "$containers" ]]; then
    docker cp $(docker ps -q --filter "name=${NAME_OF_APPLICATION}-app-"):/app/data "$BACKUP_FILE" 2>/dev/null
    if [[ $? -eq 0 ]]; then
        echo "Backup created successfully: $BACKUP_FILE"
        # Keep only last 7 backups
        ls -td "$BACKUP_DIR"/backup_* 2>/dev/null | tail -n +8 | xargs -r rm -rf
        echo "Old backups cleaned up"
    else
        echo "Backup failed!"
        exit 1
    fi
else
    echo "No running containers found. Cannot create backup."
    exit 1
fi
