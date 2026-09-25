# Railway production deployment and data-safety runbook

This application uses **one SQLite database plus persistent uploaded files**. Railway's
ephemeral filesystem must never be used for `/data`.

## 1. Production storage

Create a Railway **Volume** and mount it at:

```text
/data
```

Set:

| Variable | Required value |
|---|---|
| `DATA_DIR` | `/data` |
| `SECRET_KEY` | long random secret, 32+ chars; use 64+ random hex chars |
| `SKIP_DEMO_SEED` | `1` |
| `SESSION_COOKIE_SECURE` | `1` |
| `SQLITE_WAL` | `1` |

`/data` contains the database, secret-key fallback file, school logos, student/staff
photos, signatures, learning materials, and backups.

**Do not store `school.db` in the repository or container filesystem.**

## 2. First initialization only

For a genuinely new empty Volume, temporarily set:

```text
ALLOW_NEW_DATABASE=1
```

Deploy once. The startup guard will allow the database to be created, but it will
**not** seed the public demo account because `SKIP_DEMO_SEED=1`.

After the first successful initialization, remove `ALLOW_NEW_DATABASE`.

From then on, if `school.db` is unexpectedly missing, the deployment fails instead of
silently creating an empty database. This protects existing school data from a bad
Volume mount or an accidentally changed `DATA_DIR`.

Create the first Super Admin explicitly:

```bash
railway run python create_super_admin.py
```

Ensure the command uses the same Railway service and therefore the same `DATA_DIR=/data`.

## 3. Existing school data: safe migration

For an existing PythonAnywhere/SQLite installation:

1. Stop making application changes.
2. Make and download a verified backup of the current database.
3. Back up the `materials/`, `student_photos/`, `staff_photos/`, `signatures/`, logo
   files, and the persistent `secret_key.txt` if it is used.
4. Copy those files into the Railway Volume at `/data`.
5. Keep the same `SECRET_KEY` as the existing deployment if users/devices must remain
   authenticated. Changing it invalidates existing Flask sessions.
6. Verify `/data/school.db` with SQLite integrity check.
7. Deploy this version.

The application runs migrations **in place**. The migration code uses `ALTER TABLE`,
new tables, indexes and backfills; it does not intentionally delete school records.
The Railway startup script makes an additional SQLite online-backup snapshot before
the application is imported and migrations can run.

The new RBAC compatibility migration specifically upgrades older `role_assignments`
tables by adding missing scoped/audit columns and indexes without deleting existing
assignments or permissions.

## 4. Gunicorn production configuration

Railway starts:

```text
python railway_start.py
```

The startup script:

- verifies the persistent `/data` configuration;
- refuses an unexpected missing production database;
- runs `PRAGMA integrity_check` before an update;
- creates a verified pre-update SQLite backup;
- requires `SKIP_DEMO_SEED=1`;
- requires a strong `SECRET_KEY`;
- then starts Gunicorn.

Gunicorn uses:

- 1 worker process;
- 8 threads;
- 120-second request timeout;
- 30-second graceful shutdown;
- keep-alive 5 seconds;
- periodic worker recycling (`max-requests`) to limit long-lived process growth.

**Keep one worker process while this app uses SQLite.** Moving to multiple Gunicorn
workers is not a safe SQLite scaling change.

## 5. Health check

Railway checks:

```text
GET /healthz
```

The endpoint performs a lightweight database query and returns HTTP 200 only when the
application is serving normally. It does not require authentication.

## 6. Backups

Create verified backups with:

```bash
railway run python backup_db.py --keep 30
```

The backup uses SQLite's online-backup API and then runs `PRAGMA integrity_check`.

For production, schedule this at least daily using a Railway cron/scheduled service.
Keep backups outside the only copy of the Volume as well (for example, download/copy
verified backups to independent object storage).

A database backup alone is not a complete school-platform backup. Also preserve:

```text
/data/materials/
/data/student_photos/
/data/staff_photos/
/data/signatures/
/data/*logo* / branding files
```

and the production secret if it is stored as `secret_key.txt`.

## 7. Restore procedure

Do this during a maintenance window with the web service stopped.

First verify the chosen backup. Then:

```bash
railway run python restore_db.py   --source /data/backups/school-YYYYMMDD-HHMMSS.db   --confirm
```

`restore_db.py`:

1. refuses to operate without `--confirm`;
2. checks the source backup with `integrity_check`;
3. creates a rollback backup of the current database;
4. restores through SQLite's backup API;
5. checks the restored temporary database;
6. atomically replaces `school.db`.

Never overwrite the only copy of a database with a raw file upload.

## 8. Safe update procedure

For every production release:

### Before deployment

```bash
railway run python backup_db.py --keep 30
```

Confirm that the newest backup exists and passes integrity check.

Then deploy the new code.

### During deployment

Railway starts `railway_start.py`. It creates another pre-update backup and only then
imports `app.py`, which runs migrations.

If the application fails to boot, **do not delete or recreate `/data/school.db`**.
Inspect the logs and use the pre-update backup if a rollback is required.

### After deployment

Check:

```text
GET /healthz
```

Then log in and verify, in read-only fashion first:

- schools;
- users/roles;
- students;
- sessions/terms;
- scores/results;
- attendance;
- uploaded learning materials;
- parent/student access;
- offline sync.

Only after verification should normal data entry resume.

## 9. Rollback

A code rollback and a database rollback are different operations.

If the new code fails but its migrations are backward-compatible, first roll back the
application code while preserving `/data`.

If the database schema itself must be rolled back, do **not** simply deploy old code
against the newer schema. Restore the pre-update database backup during a maintenance
window, and restore the matching uploaded files if they changed.

The startup backup made immediately before migration is intended to make this recovery
possible.

## 10. Important data-safety rules

- Never run a production `init_db(reset=True)`.
- Never remove the Railway Volume during a deployment.
- Never remove `school.db` to "fix" a failed boot.
- Never unset `DATA_DIR` in production.
- Never remove `SKIP_DEMO_SEED=1` from a public deployment.
- Do not change `SECRET_KEY` casually.
- Keep only one Gunicorn worker with SQLite.
- Keep independent off-Volume backups.
- Test a restore periodically, not only the backup command.
- Do not deploy schema changes without a tested migration and a verified backup.

## 11. Moving away from SQLite

When the platform needs multiple application workers or high concurrent write volume,
move the central database to PostgreSQL rather than increasing Gunicorn workers.
This application uses SQLite-specific SQL and triggers, so that migration requires a
deliberate database-porting project rather than changing one environment variable.
