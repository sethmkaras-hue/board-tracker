# Deploy on RHEL with rootless Podman

The production stack targets Podman 4.9.4-rhel and podman-compose 1.0.6. Run Compose as one dedicated, unprivileged Linux service account. The Nginx service publishes HTTP and HTTPS. FastAPI listens on port 8000 on the Compose bridge, and the notification worker shares the backend image without a listener. Both Python services connect to an existing PostgreSQL database. The frontend build runs npm and TypeScript inside a Node 22 image and ships only static assets with Nginx. Host Node.js 16.20.2 is sufficient because deployment never invokes it.

## RHEL prerequisites

Install Podman and rootless networking support from your RHEL repositories, including the appropriate Netavark and Aardvark DNS packages. Install podman-compose 1.0.6 through an approved package or Python environment. Verify `podman --version`, `podman-compose --version`, and that the application user has a valid `/etc/subuid` and `/etc/subgid` allocation. Check `podman info` reports rootless mode under that user. Use an approved PostgreSQL client package providing `pg_dump`, `pg_restore`, and `psql` for backups, and install `flock` from util-linux. The `pg_dump` major version must be at least the server major version.

Place the checkout at `~/board-tracker` for the included systemd units. All Compose examples run from the repository root. For new installations, prepare the protected files and required bind mount directories.

```sh
install -m 600 .env.example .env
install -m 600 deploy/ldap.env.example deploy/ldap.env
install -m 600 deploy/smtp.env.example deploy/smtp.env
install -d -m 700 deploy/tls
install -d -m 755 deploy/trust deploy/backup-status
```

Use literal `KEY=value` lines in the Podman env files. Avoid shell quoting, inline comments, and variable expansion in values. Compose 1.0.6 can log generated commands, so credentials are passed using Podman env files rather than command-line environment flags. Restrict access to the service account, its container metadata, and the env files.

## PostgreSQL

Set `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env`. The application builds the SQLAlchemy URL, including passwords with URL punctuation. Use an existing, dedicated application database and login. The role running migrations needs permission to create and change objects in the application's schema. A DBA can run the migration with an owner account by setting separate credentials in an operator-only env file and running the backend image with that file. The runtime login then needs table and sequence access, with only SELECT and INSERT on audit events. The migration installs the append-only database trigger.

- For PostgreSQL on the RHEL host, first try `host.containers.internal`. Container `localhost` refers to the container, and the gateway alias does not guarantee access to a service listening only on host loopback. Bind PostgreSQL to an interface reachable from the rootless network as approved by your DBA, or use the RHEL host's reachable DNS name or IP. Verify which address the login reaches and make sure the certificate matches it.
- For remote PostgreSQL, use its reachable hostname or IP directly. Set `POSTGRES_SSLMODE=verify-full` for remote production connections and, if needed, set `POSTGRES_SSLROOTCERT=/certs/postgres-ca.pem` with the CA file in `deploy/trust`.
- Coordinate the listening address, `pg_hba.conf`, and the host or database firewall with the DBA. Allow the actual source address seen by PostgreSQL. Rootless networking may translate it. Check the DNS name and route from the container when the host shell can connect but the backend cannot.

## HTTPS, SELinux, LDAP, and SMTP

Place the server certificate chain and private key at `deploy/tls/fullchain.pem` and `deploy/tls/privkey.pem`. Keep the key mode 0600 and owned by the rootless service account. Set `PUBLIC_URL` to the external HTTPS origin without a trailing slash. It controls HTTP redirects and links in daily digests. Example `https://board-tracker.corp.example:8443`. The published ports default to 8080 and 8443 for rootless operation. If standard ports are required, use an existing approved host proxy or port-forwarding policy. Allow inbound access to the published ports from the internal engineering network in the relevant firewalld zone. Keep port 8000 off the host.

Use dedicated paths for mounts so Podman can relabel them. The TLS mount is private (`:Z`). The trust and backup-status mounts use shared labels (`:z`) so one-off backend commands do not relabel files away from the running services. Trust files and their directory must be readable and traversable by the non-root container processes. Keep SELinux enforcing. If startup logs show a permissions error, check ownership, modes, and the SELinux context with `ls -lZ` and review AVC denials before adjusting policy. Avoid relabeling unrelated home or system directories. The bridge requires DNS resolution for `backend` and outbound access to the configured database, LDAP, and SMTP destinations. Nginx re-resolves the backend service name after restarts or recreation.

In `deploy/ldap.env`, set `LDAP_URL` to `ldaps://...` or use `ldap://...` with `LDAP_STARTTLS=true`. Supply `LDAP_BASE_DN`, `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, and the username attribute used by the directory. For an internal CA, put its certificate in `deploy/trust` and set `LDAP_CA_FILE=/certs/ldap-ca.pem`. Keep `DEV_AUTH=0`. After the intended administrator signs in with a directory identity that includes an email address, run `podman-compose exec backend python -m tracker.manage bootstrap-admin corporate.username`.

Set `SMTP_HOST` in `.env`. In `deploy/smtp.env`, set `SMTP_PORT` and `SMTP_FROM`. For an approved unauthenticated plain relay, leave `SMTP_STARTTLS=false` and credentials blank. For STARTTLS, set `SMTP_STARTTLS=true`, specify a CA with `SMTP_CA_FILE` if needed, and supply `SMTP_USERNAME` and `SMTP_PASSWORD` when the relay requires them. For implicit TLS, set `SMTP_TLS=implicit` and the appropriate port. Credentials require TLS. The legacy `SMTP_TLS` values `starttls` and `none` also work as explicit overrides.

## Build, migrate, and start

```sh
podman-compose build
podman-compose run --rm backend python -m tracker.diagnostics db
podman-compose run --rm backend alembic upgrade head
podman-compose up -d
podman-compose ps
podman-compose logs backend
podman-compose logs worker
podman-compose logs web
```

For an approved HTTPS build proxy with a private CA, use the same image tags as Compose and pass the trusted PEM bundle as a build secret:

```sh
podman build --secret id=build_ca,src=/path/to/trusted-ca-bundle.pem -t localhost/board-tracker-backend:1 backend
podman build --secret id=build_ca,src=/path/to/trusted-ca-bundle.pem -t localhost/board-tracker-web:1 -f frontend/Dockerfile .
```

Check each build exit report and the database migration before proceeding. The migration only creates or upgrades application objects and must succeed before the services start. Check `/api/health` over HTTPS using the appropriate trusted CA. Then verify a real directory sign-in. Diagnostics can run even if the regular services are stopped.

```sh
podman-compose run --rm backend python -m tracker.diagnostics ldap
podman-compose run --rm worker python -m tracker.diagnostics smtp
podman-compose run --rm worker python -m tracker.diagnostics smtp --send-to designated.test.recipient@example.invalid
```

The LDAP diagnostic tests the encrypted service bind, and a real user sign-in tests user lookup and bind. The SMTP diagnostic defaults to a connection and NOOP check. Explicitly providing an approved test recipient exercises message delivery. Check the recipient inbox and relay logs to confirm final delivery. When diagnosing PostgreSQL, compare the connection probe with the database logs for TLS or access failures. When Nginx returns 502, check `podman-compose ps`, the backend logs, and that Aardvark DNS resolves `backend` on the named bridge.

For a manual deployment, `podman-compose restart backend worker web` restarts containers. `podman-compose stop` stops them. Environment updates require recreation with `podman-compose up -d --force-recreate`. With systemd enabled, use `systemctl --user stop board-tracker.service` for an intentional stop.

## Automatic startup and notifications

Install the supplied units into `~/.config/systemd/user`. Update `WorkingDirectory` if the checkout is elsewhere. Update `ExecStart` and `ExecStop` to the absolute path reported by `command -v podman-compose`. Run these commands as the service user except for enabling lingering, which requires an authorized administrator.

```sh
install -d -m 700 ~/.config/systemd/user
install -m 644 deploy/systemd/* ~/.config/systemd/user/
sudo loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now board-tracker.service
systemctl --user status board-tracker.service
```

The lingering user manager starts the Compose stack after boot and continues after logout. Compose restart policies recover containers from process exits. The worker independently checks the configured local midnight every minute. Set `NOTIFICATION_TIMEZONE` in `.env` or override it through Administration. The database stores the cycle boundary, unique daily digest records, and retry state. After downtime the next run consolidates changes since the previous successful cycle. An SMTP relay can accept a message before a success is persisted. The stable Message-ID supports relay deduplication if the relay implements it.

## Backups and restore

Use a separate login approved by the DBA that can read all objects to be backed up. Copy `deploy/backup.env.example` to `~/.config/board-tracker/backup.env` with mode 0600 and fill in the host-side libpq connection settings, retention, status directory, and persistent dump directory. Host-side backup commands may use `localhost` when PostgreSQL runs on the same RHEL host. Set `PGPASSFILE` to a mode-0600 file containing `host:port:database:user:password`. Follow libpq escaping rules for literal colons and backslashes. Keep the dumps outside the checkout and on storage with restricted access. Use off-host storage to protect against host loss.

Make sure `BACKUP_STATUS_DIR` matches the host path mounted by Compose. Only the status file is shared with the backend. Enable and test the timer.

```sh
systemctl --user enable --now board-tracker-backup.timer
systemctl --user start board-tracker-backup.service
systemctl --user list-timers board-tracker-backup.timer
journalctl --user -u board-tracker-backup.service
```

The timer runs daily at 02:00 UTC and catches up after downtime. Change `OnCalendar` with `systemctl --user edit board-tracker-backup.timer` by clearing the inherited value with `OnCalendar=` before setting the new schedule. The backup command uses a lock and only replaces a dump after both the archive directory and contents can be read. Failed backups retain previous dumps and write a failure to the journal and status file.

For a restore exercise, ask the DBA to create an empty disposable database and enable an authorized restore login. Set host-side libpq variables for that destination and run the following. Use a current known-good archive and verify that the target is the disposable database before proceeding.

```sh
pg_restore --list /protected/path/tracker-YYYY-MM-DD.dump
pg_restore --no-password --exit-on-error --no-owner --no-privileges \
  --dbname=tracker_restore /protected/path/tracker-YYYY-MM-DD.dump
psql --dbname=tracker_restore --command='SELECT count(*) FROM boards; SELECT count(*) FROM audit_events;'
```

Compare counts and inspect representative records and the audit trigger. For production recovery, stop the app and worker, have the DBA restore and reapply database grants, and invalidate restored application sessions. Review queued digests against relay logs before enabling the worker. Point both application services and the backup configuration at the verified database.

## Upgrades

Take and verify a backup before changing code. Stop the old services, update the checkout, rebuild, run `podman-compose run --rm backend alembic upgrade head`, and restart. If the migration fails, keep application traffic stopped and investigate before retrying. With systemd enabled, start the stack with `systemctl --user start board-tracker.service` after migrating. Verify the health endpoint, logs, and a representative board.

If moving from the earlier bundled PostgreSQL deployment, stop the old app and worker using the old configuration, then take a logical dump of that database and restore it into the externally managed database before applying migrations. Retain the old database volume until the external database has been verified. The new stack has no database service or database volume.
