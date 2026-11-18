# Implementation status

**Tested** means an automated check or an operational smoke test exercised the listed behavior. **Implemented** means code is present and the row identifies coverage gaps. **Blocked** identifies an external prerequisite. **Pending** identifies follow-up work.

| Specification | Status | Evidence and scope |
| --- | --- | --- |
| 1. Technology stack | Tested | React, TypeScript, Vite, Tailwind, shadcn/ui button, TanStack Table, and Recharts build. FastAPI, SQLAlchemy, Alembic, and PostgreSQL run. |
| 2. Board identification and lifecycle | Tested | Required fields, identifier format, duplicates, revision links, active default, delete and restore visibility. |
| 3. Board fields | Tested | API and forms cover engineering fields and URLs. Tests cover invalid URLs, UTF-8 notes limits, and nullable fields. Browser stores the display timezone. |
| 4. Parent systems | Tested | Multiple relationships, independent quantities, nonnegative validation, editing, and Excel output. The API and UI also support removal. |
| 5. Programs | Tested | Shared program updates and many-to-many relationships, including browser creation and linking. |
| 6. Review and verification | Tested | Five independently editable steps with current state and nullable date. The API preserves previous values in audit. |
| 7. LDAP and sessions | Tested | Mock directory bind, escaped lookup, production development-auth rejection, session expiry, and CSRF checks. |
| 7. Live corporate LDAP | Blocked | Requires the organization's endpoint, certificate trust chain, bind setup, and designated test account. |
| 8. Authorization | Tested | Protected endpoints, administrator-only lifecycle actions, and deleted record visibility. Admin bootstrap and role management are implemented. |
| 9. Activity history | Tested | Audit events commit with domain changes and preserve actor identity and field values. The PostgreSQL trigger rejects updates and deletes. |
| 10. Concurrent editing | Tested | Simultaneous disjoint PostgreSQL edits, stale same-field conflicts, and explicit overwrite. Frontend tests verify conflict details and the overwrite request. |
| 11. Dashboard | Tested | Browser loads metric cards, charts, and recent records. The charts link to corresponding filters. |
| 12. Search and saved views | Tested | AND/OR filter combinations, inclusive dates, current-value activity searches, saved view isolation, and debounced shareable search. |
| 13. Board detail | Tested | Browser opens detail, edits notes and verification, and follows board and program links. Inline editing and activity pagination are implemented. |
| 14. Program dashboard | Tested | Browser opens program detail. API test verifies associated boards. Maturity, review, and verification charts use program-scoped data. |
| 15. Notifications | Tested | Midnight cutoff, current and deletion-time recipient resolution, deduplication, in-app read state, SMTP message construction, and retry behavior with a simulated relay failure. |
| 15. Live corporate SMTP | Blocked | Requires the organization's relay hostname, sending policy, trust chain, and a designated recipient. |
| 16. Exports | Tested | CSV and XLSX use all filtered matches. Tests verify worksheets, hyperlinks, formula hardening, and separate history export. |
| 17. Administration | Implemented | User directory, deleted board view, timezone configuration, service configuration indicators, backup status, and digest job and failure views. Automated tests cover permissions and board restoration. |
| 18. Database and backups | Tested | Alembic upgrades and downgrades on PostgreSQL and schema drift check. A readable dump restored into a separate database with 18 boards, 90 reviews, 151 audit rows, and the immutable audit trigger. |
| 19. Security | Tested | Backend authorization, secure production cookie settings, CSRF, directory transport configuration, rate limits, safe URLs, and sanitized validation errors. The deployment guide documents the data access model. |
| 20. User experience | Implemented | Responsive layout, themes, confirmations, unsaved-change prompts, searchable people controls, dates, loading states, and errors. Editor behavior is covered by React Testing Library and browser tests. |
| 21. Automated tests | Tested | pytest with PostgreSQL, Vitest and React Testing Library, and Playwright with system Chromium. |
| 22. Development and deployment | Tested | Development seed and startup, Docker builds, deployment configuration, HTTPS startup with Docker Compose, restricted runtime database role, and database restore. Corporate deployment values are supplied by the operator. |
| 23. Implementation process | Tested | Foundation, workflow, UI, worker, and deployment were exercised as they were built. See the README for implementation assumptions. |
| 24. Repository deliverables | Implemented | Source, migrations, tests, Docker Compose, environment template, development instructions, deployment runbook, and this status file. |
| Production acceptance | Pending | Validate corporate LDAP and SMTP, production DNS and certificate installation, and off-host retention under the organization's operating procedures. |

## Operating assumptions

- The application maintains a directory of people who have signed in at least once. Programs and assignments use that directory.
- Inactivity means 30 days without board-related audit activity. Timezone preferences are local to the browser.
- The scheduler catches up from the most recent successful cycle when it restarts. An SMTP relay may accept a message before the application can record success. The stable Message-ID supports relay deduplication when available.
- Application users have no direct database access. The deployment operator controls database credentials, backups, and restore.
