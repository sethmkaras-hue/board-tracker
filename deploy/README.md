# Deployment and operations

## Production installation

1. Install Docker Engine and the Compose plugin on the internal Linux host. Configure internal DNS and host firewall rules for HTTPS. PostgreSQL and the API do not publish host ports.
2. Run `cp .env.example .env && chmod 600 .env`. Set distinct strong owner and application passwords. Set the owner password in `POSTGRES_PASSWORD` and URL-encode it in `MIGRATION_DATABASE_URL`. URL-encode the application password in `DATABASE_URL`. The migration service provisions the restricted runtime role from that URL. Quote values with literal shell or Compose interpolation characters according to Compose dotenv syntax. Avoid putting secrets in shell history or source control.
3. Create `deploy/trust` for LDAP and SMTP CA bundles. Place the CA-signed certificate chain and private key at `deploy/tls/fullchain.pem` and `deploy/tls/privkey.pem`. Give the Nginx container access to the key and restrict access on the host. Set `PUBLIC_URL` to the HTTPS base URL.
4. Configure LDAP and SMTP using the sections below. Leave `DEV_AUTH=0` and `DEV_NOTIFICATIONS=0`. Production application startup rejects development authentication.
5. Run `docker compose up -d --build`. The migration service applies Alembic before the API and worker start. Use `docker compose ps -a` to check that migrations completed and the API is healthy. Make an HTTPS request to `/api/health` and verify a real directory sign-in.

An approved build proxy CA bundle can be passed without embedding it in images. For example, run `docker build --secret id=build_ca,src=/path/to/trusted-ca-bundle -t board-tracker-api backend` or `docker build --secret id=build_ca,src=/path/to/trusted-ca-bundle -f frontend/Dockerfile -t board-tracker-web .`. To use the secret with Compose, add it as a build secret named `build_ca` on the backend and frontend builds.

## LDAP and initial administrator

Use `LDAP_URL=ldaps://directory-host:636` or `LDAP_URL=ldap://directory-host:389` with `LDAP_STARTTLS=1`. Set `LDAP_BASE_DN`, read-only `LDAP_BIND_DN`, and `LDAP_BIND_PASSWORD`. The search account needs permission to find the username, display name, mail, and entry DN. Set `LDAP_USERNAME_ATTRIBUTE` to the matching attribute, commonly `sAMAccountName` or `uid`. Mount the directory trust bundle as `deploy/trust/ldap-ca.pem` or use a trusted system CA. The server certificate must match the LDAP host. The application binds separately as the user's LDAP entry to verify the submitted password and stores session token hashes instead of passwords.

Have the designated administrator sign in once and verify their LDAP directory email. A server operator then runs `docker compose exec api python -m tracker.manage bootstrap-admin corporate.username`. The operation is audited against that directory identity. Additional grants and revocations are managed through the administrative user directory.

## SMTP and scheduling

Set `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM`. STARTTLS is the default. Set `SMTP_TLS=implicit` for a relay on port 465, or `SMTP_TLS=none` only for an internal relay explicitly authorized for unauthenticated cleartext transport. Set `SMTP_USERNAME` and `SMTP_PASSWORD` together if required, and provide `SMTP_CA_FILE` for an internal certificate authority.

The worker checks once per minute for the current local day. It processes audit events before local midnight exactly once per digest cycle, including backlog following downtime. The timezone is configured by `NOTIFICATION_TIMEZONE` or through Administration. SMTP is separate from generation. The worker retries temporary failures with exponential backoff and records the final failure after ten attempts. Each digest has a stable Message-ID. SMTP may deliver a duplicate if the worker dies after the relay accepts the message and before it records success. In-app digest creation is database-deduplicated. A deletion digest uses the assignments captured at deletion. Ordinary users can read that notification but opening its deleted record still requires administrator access.

## Backup and restore

The backup container takes a daily custom-format PostgreSQL dump. It uses UTC and `BACKUP_HOUR_UTC` with retention set by `BACKUP_RETENTION_DAYS`. The backup volume is separate from the primary database volume. Backup status records verification only after `pg_restore` can read the archive and all of its contents. Monitor backup age and copy dumps to separately protected storage to survive host loss.

Run an on-demand backup with `docker compose exec backup sh /scripts/backup.sh`. Restore into an isolated database first. Substitute the verified dump filename in the following commands.

```sh
docker compose exec backup cat /backups/status
docker compose exec -T backup cat /backups/tracker-YYYY-MM-DD.dump > tracker-restore.dump
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" tracker_restore'
docker compose exec -T db sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d tracker_restore' < tracker-restore.dump
docker compose exec db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d tracker_restore -c "SELECT count(*) FROM boards; SELECT count(*) FROM reviews; SELECT count(*) FROM audit_events;"'
```

Compare counts and representative board, program, and review records with the source, and check that `immutable_audit` exists in `pg_trigger`. To recover a production outage, stop API and worker containers before repointing `DATABASE_URL` and `MIGRATION_DATABASE_URL` at the verified restored database. Invalidate restored sessions with `DELETE FROM sessions` before enabling traffic. Review queued or previously sent digests against the relay logs before restarting the worker. Apply migrations and verify HTTPS health, authentication, and a representative board. Keep the original database volume until recovery is verified.
