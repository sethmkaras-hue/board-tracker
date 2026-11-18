#!/bin/sh
set -eu
umask 077
export PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
retention=${BACKUP_RETENTION_DAYS:-14}
case "$retention" in ''|*[!0-9]*) exit 2;; esac
destination="/backups/tracker-$(date -u +%F).dump"
temp=$(mktemp /backups/.tracker.XXXXXX)
status=$(mktemp /backups/.status.XXXXXX)
cleanup() {
  rm -f "$temp" "$status"
}
trap cleanup EXIT
if pg_dump --format=custom --file="$temp" "$POSTGRES_DB" &&
   pg_restore --list "$temp" >/dev/null &&
   pg_restore --file=/dev/null "$temp"; then
  mv "$temp" "$destination"
  find /backups -type f -name 'tracker-*.dump' -mtime "+$retention" -delete
  printf 'Verified readable dump at %s UTC\n' "$(date -u +'%F %T')" > "$status"
else
  printf 'Backup failed at %s UTC\n' "$(date -u +'%F %T')" > "$status"
  cat "$status" >&2
  chmod 644 "$status"
  mv "$status" /backups/status
  exit 1
fi
chmod 644 "$status"
mv "$status" /backups/status
