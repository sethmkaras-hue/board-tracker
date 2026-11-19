# Ubuntu home testing

Run these commands on the Ubuntu server from the repository root. The home stack serves the built frontend and FastAPI over local HTTP. It uses the PostgreSQL database already installed on Ubuntu and starts no database, LDAP, SMTP, or notification containers.

## 1. Check tooling and configure the environment

```sh
command -v podman
command -v podman-compose
```

If a command is missing, install its Ubuntu package. Use `sudo apt update`, then `sudo apt install podman`, `sudo apt install podman-compose`, or both as needed. Ubuntu releases without a `podman-compose` package can install it with `pipx install podman-compose` after installing `pipx` and configuring its executable path. Run Podman and Compose as the same normal user throughout.

Create `.env` from [.env.home.example](../.env.home.example). If you already have a `.env`, save a protected copy before editing.

```sh
install -m 600 .env.home.example .env  # New file only
```

Set `POSTGRES_USER` to `branden` and `POSTGRES_PASSWORD` to the existing local PostgreSQL password. Keep the supplied database name and port. Set two different, non-placeholder values for `HOME_ADMIN_PASSWORD` and `HOME_USER_PASSWORD`. The home manifest selects development authentication explicitly. Log in as `home.admin` or `home.user` with the corresponding password. Accounts are created on first login. Use the home stack only with a test database and reserve those two usernames for home authentication.

## 2. Check host PostgreSQL access

```sh
podman-compose -p board-tracker-home -f compose.home.yml build
podman-compose -p board-tracker-home -f compose.home.yml run --rm backend python -m tracker.diagnostics dns
podman-compose -p board-tracker-home -f compose.home.yml run --rm backend python -m tracker.diagnostics db
```

The DNS command prints the address resolved inside the backend container. The database command opens a PostgreSQL connection with the configured login and runs `SELECT 1`. Resolve failures before migrating.

The manifest requests Podman's `host-gateway` mapping for `host.containers.internal`. Container loopback addresses are local to the container. If Podman cannot determine the host gateway, inspect the actual network and host interfaces. If your Podman version already provides a working automatic alias, remove the explicit `extra_hosts` entry from your local manifest. Otherwise use a specific host address reachable from the container in `POSTGRES_HOST`, and remove the explicit alias if it prevents the container from starting.

```sh
podman network ls
podman network inspect <home-network-from-list>
ip -brief address
sudo ss -ltnp 'sport = :5432'
pg_lsclusters
sudo -u postgres psql -X -p 5432 -Atc 'SHOW config_file; SHOW hba_file; SHOW listen_addresses;'
```

Check the network's reported subnet and gateway and the PostgreSQL log for the actual client address. Rootless routing can translate the client address, and the gateway may be inside a separate network namespace. Use the observed source and reachable host address when configuring PostgreSQL.

Only edit PostgreSQL configuration if the container probe requires it. Back up the actual files reported above with `sudo cp -a <file> <file>.before-board-tracker` before making changes.

1. If the connection is refused because PostgreSQL listens only on loopback, add the specific reachable host interface address to `listen_addresses` while retaining any existing bindings. Restart only the identified cluster using `sudo pg_ctlcluster <version> <cluster> restart`.
2. If PostgreSQL reports that no HBA entry matches, add a rule such as `host circuit_card_tracking branden <verified-client-CIDR> scram-sha-256` in the actual `pg_hba.conf` ahead of any matching rejection. Use a single-address CIDR when possible or the verified dedicated container subnet. Reload HBA changes with `sudo pg_ctlcluster <version> <cluster> reload`.
3. If UFW blocks the route, scope any allow rule to the verified source, intended host destination, and TCP port 5432. Preserve the firewall and existing rules. Do not bind PostgreSQL to every interface or allow the whole home LAN. If rootless translation makes the source ambiguous, resolve the route before broadening access.

Rerun the container DNS and database probes after any network changes.

## 3. Migrate, verify, and launch

```sh
podman-compose -p board-tracker-home -f compose.home.yml run --rm backend alembic upgrade head
podman-compose -p board-tracker-home -f compose.home.yml run --rm backend python -m tracker.diagnostics schema
podman-compose -p board-tracker-home -f compose.home.yml up -d
curl -fsS http://127.0.0.1:8081/api/health
```

The migration upgrades the existing application schema and the schema check verifies the expected application tables and Alembic head. If Alembic reports an unexpected revision or conflicting existing tables, investigate the database history before retrying. Avoid resetting the database or stamping an unverified schema.

From the server, open `http://127.0.0.1:8081`. From another machine, forward the loopback port over SSH and open the same URL on that machine.

```sh
ssh -N -L 8081:127.0.0.1:8081 your-user@your-ubuntu-server
```

Check that both accounts can sign in and use boards. A regular user can create a board and edit it, while deleting or restoring a board requires the administrator. The home HTTP listener stays on loopback because development sessions use HTTP cookies. Change `HOME_HTTP_PORT` if needed and adjust the commands and tunnel accordingly.

Use `podman-compose -p board-tracker-home -f compose.home.yml ps` and `podman-compose -p board-tracker-home -f compose.home.yml logs backend` for diagnostics. Stop the stack with `podman-compose -p board-tracker-home -f compose.home.yml down`. The PostgreSQL database runs independently of the stack.
