# BRANDEN

BRANDEN (Board Review, Analysis, and Design Engineering Navigator) is an internal engineering workspace for circuit card design records, independent revisions, ownership, program associations, parent quantities, and review and verification history.

## RHEL deployment

Production uses rootless Podman 4.9.4-rhel, podman-compose 1.0.6, and an externally managed PostgreSQL database. Nginx serves the frontend and proxies FastAPI on a private container network. Node 22 runs in the frontend build stage. The host Node.js version is independent of deployment.

Create the three protected env files and install the TLS certificates as described in the [RHEL deployment and operations guide](deploy/README.md). The guide covers PostgreSQL and Podman host-gateway access, LDAP, SMTP, SELinux, rootless ports, upgrades, systemd, backups, restoration, and diagnostics.

```sh
podman-compose build
podman-compose run --rm backend python -m tracker.diagnostics db
podman-compose run --rm backend alembic upgrade head
podman-compose up -d
```

## Native development

For local source development, use Python 3.12 or newer, Node 22 or newer, and an existing PostgreSQL development database. From the checkout:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend ci
```

Start the API from the repository root. Use the illustrated password only on a local development instance.

```sh
export DATABASE_URL=postgresql+psycopg://tracker:tracker@127.0.0.1:55432/tracker
export APP_ENV=development DEV_AUTH=1 DEV_PASSWORD=local-only
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/python -m tracker.manage seed
../.venv/bin/uvicorn tracker.main:app --reload --no-access-log
```

In another terminal, run `npm --prefix frontend run dev` and open the URL printed by Vite. Sign in as `demo.admin` with `DEV_PASSWORD`. The optional seed command creates explicitly synthetic users, boards, and programs. Live development emails are disabled by default. People become available for assignment after their first directory sign-in.

Run checks from the root.

```sh
(cd backend && ../.venv/bin/pytest -q)
npm --prefix frontend run test
npm --prefix frontend run build

# Use a separate disposable PostgreSQL database. Tests drop the application schema.
createdb -h 127.0.0.1 -p 55432 -U tracker tracker_test
(cd backend && TEST_DATABASE_URL=postgresql+psycopg://tracker:tracker@127.0.0.1:55432/tracker_test ../.venv/bin/pytest -q)

# With the seeded API and Vite running:
(cd frontend && npx playwright install chromium)
E2E_DEV_PASSWORD=local-only npm --prefix frontend run e2e
```

Playwright also accepts `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` for a system Chromium and `E2E_BASE_URL` for a dedicated development instance. The browser tests intentionally create synthetic records.

## Architecture and behavior

- `backend/tracker` contains the FastAPI interface, LDAP and session handling, SQLAlchemy models, board services, notifications, and management commands.
- `backend/alembic` contains the database migrations. Boards, programs, parent systems, reviews, and people have separate relational records. The association tables keep assignments and program membership normalized.
- `frontend` contains the Vite and React app with Tailwind CSS, a shadcn/ui button, TanStack Table, and Recharts.
- `deploy` contains HTTPS proxy and database backup configuration. See [Deployment and operations](deploy/README.md) and [Implementation status](IMPLEMENTATION_STATUS.md).

The product uses calendar dates for reviews and UTC instants for audit events. Timestamps display in the browser’s local timezone. Timestamp search ranges include both selected calendar dates and default to the browser timezone. Shared and saved searches keep any timezone recorded in the URL. Search always evaluates the current record attributes. The dashboard's inactivity threshold is 30 days since the last board-related audit event.

Updates submit changed fields with their original values. PostgreSQL coordinates writes with a short transaction lock shared by audit-producing requests and digest generation. A same-field stale edit returns both values. Changing separate fields preserves both updates. PostgreSQL blocks updates and deletes on audit rows with a trigger.

LDAP login and administrator privileges do not enforce export-control or program-specific need-to-know restrictions. All authenticated users can open ordinary boards and export the data they can view. Define and implement any additional access policy before storing data that requires it.

For local testing without corporate LDAP or SMTP, use the [Ubuntu home deployment guide](deploy/HOME.md).

## Review and maturity upgrade

Apply Alembic revision `9f2618a85e01` before starting the updated API. Use the deployment migration command with the existing migration database credentials.

```sh
podman-compose run --rm backend alembic upgrade head
```

The migration adds a nullable review hyperlink and widens review state storage for **Working Action Items**. Existing review dates, states, and audit entries keep their original values. The downgrade refuses to run while a review hyperlink or a newly supported state would be lost. Keep a verified pre-upgrade backup for rollback.

Board creation now requires a `reviews` object keyed by the five review names. Each entry requires an ISO calendar date and accepts an optional state and HTTP or HTTPS URL. State defaults to **Not Started**. Existing reviews can still have a blank date and remain editable.

Maturity selection and API writes accept 1 through 4 or an unspecified value. The database retains support for reading existing zero-valued records so the migration can preserve them. Check each deployment for any such boards, including deleted boards.

```sql
SELECT identifier, deleted_at
FROM boards
WHERE maturity = 0
ORDER BY identifier;
```

Have the record owner determine the appropriate maturity for each result. An authorized edit records the change in the board’s audit history. Both PostgreSQL smoke-test databases available in this workspace returned zero matches. Run the query on the deployment database before rollout.

## Program review timeline

Program Detail shows all currently associated boards on the same calendar axis. The page rechecks the program every 30 seconds while visible and when the browser tab regains focus. Boards with undated reviews remain listed. Program Activity History covers updates to the program itself and activity on currently associated boards. Its CSV and Excel exports use the same scope.
