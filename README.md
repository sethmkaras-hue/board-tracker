# Board Tracker

Board Tracker is an internal engineering workspace for circuit card design records, independent revisions, ownership, program associations, parent quantities, and review and verification history.

## Development

Prerequisites are Python 3.12 or newer, Node 22 or newer, and PostgreSQL 16. Run these commands from the existing checkout.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend ci

docker run --rm -d --name board-tracker-db \
  -e POSTGRES_USER=tracker -e POSTGRES_PASSWORD=tracker -e POSTGRES_DB=tracker \
  -p 127.0.0.1:55432:5432 postgres:16-alpine
docker exec board-tracker-db pg_isready -U tracker -d tracker
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
docker exec board-tracker-db createdb -U tracker tracker_test
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

The product uses calendar dates for reviews and UTC instants for audit events. The browser stores a display timezone preference. Timestamp search ranges include both selected calendar dates in the timezone in the search URL. Search always evaluates the current record attributes. The dashboard's inactivity threshold is 30 days since the last board-related audit event.

Updates submit changed fields with their original values. PostgreSQL coordinates writes with a short transaction lock shared by audit-producing requests and digest generation. A same-field stale edit returns both values. Changing separate fields preserves both updates. PostgreSQL blocks updates and deletes on audit rows with a trigger.

LDAP login and administrator privileges do not enforce export-control or program-specific need-to-know restrictions. All authenticated users can open ordinary boards and export the data they can view. Define and implement any additional access policy before storing data that requires it.
