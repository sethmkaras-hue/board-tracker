#!/bin/sh
set -eu
umask 077

: "${BACKUP_DIR:?Set BACKUP_DIR to a persistent host directory}"
: "${BACKUP_STATUS_DIR:?Set BACKUP_STATUS_DIR to the status mount directory}"
: "${PGHOST:?Set PGHOST}"
: "${PGDATABASE:?Set PGDATABASE}"
: "${PGUSER:?Set PGUSER}"
: "${PGPASSFILE:?Set PGPASSFILE to a protected password file}"
retention=${BACKUP_RETENTION_DAYS:-14}
case "$retention" in
  ''|*[!0-9]*) echo "Invalid backup retention" >&2; exit 2 ;;
esac

mkdir -p "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.backup.lock"
flock -n 9 || { echo "Backup already running"; exit 0; }

dump=$(mktemp "$BACKUP_DIR/.dump.XXXXXX")
status=$(mktemp "$BACKUP_STATUS_DIR/.status.XXXXXX")
trap 'rm -f "$dump" "$status"' EXIT

publish_status() {
  printf '%s at %s UTC\n' "$1" "$(date -u +'%F %T')" > "$status"
  chmod 644 "$status"
  mv -f "$status" "$BACKUP_STATUS_DIR/status"
}

if pg_dump --no-password --format=custom --file="$dump" &&
   pg_restore --list "$dump" >/dev/null &&
   pg_restore --file=/dev/null "$dump"; then
  mv -f "$dump" "$BACKUP_DIR/tracker-$(date -u +%F).dump"
  publish_status "Verified readable dump"
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'tracker-????-??-??.dump' -mtime "+$retention" -delete
  echo "Board Tracker backup verified"
else
  publish_status "Backup failed"
  echo "Board Tracker backup failed; previous dumps retained" >&2
  exit 1
fi
