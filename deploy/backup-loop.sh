#!/bin/sh
set -eu
hour=${BACKUP_HOUR_UTC:-2}
case "$hour" in
  [0-9]) hour="0$hour";;
  [01][0-9]|2[0-3]) ;;
  *) echo "Invalid BACKUP_HOUR_UTC" >&2; exit 2;;
esac
while true; do
  today=$(date -u +%F)
  current=$(date -u +%H)
  if [ "$current" -ge "$hour" ] && [ ! -f "/backups/tracker-$today.dump" ]; then
    /bin/sh /scripts/backup.sh || sleep 240
  fi
  sleep 60
done
