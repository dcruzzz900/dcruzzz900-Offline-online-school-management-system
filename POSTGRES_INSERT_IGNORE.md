# PostgreSQL INSERT OR IGNORE compatibility

The PostgreSQL DB-API adapter translates a leading `INSERT OR IGNORE INTO`
clause to `INSERT INTO ... ON CONFLICT DO NOTHING`. This allows the existing
qmark SQL to be converted to psycopg placeholders in the same execution path.

## Important semantic boundary

This is a compatibility bridge, not a blanket proof of identical SQLite
semantics. PostgreSQL `ON CONFLICT DO NOTHING` suppresses unique and exclusion
conflicts. SQLite `INSERT OR IGNORE` may also suppress CHECK and NOT NULL
violations (foreign-key violations are not ignored). Review each call site's
target table constraints and input validation before enabling it on PostgreSQL.

`INSERT OR REPLACE` is not rewritten. It is rejected with
`NotImplementedError` until the application defines an explicit conflict
identity and update policy for that statement. Do not replace it with
`ON CONFLICT DO UPDATE` without confirming delete/insert side effects,
foreign-key behaviour, triggers, and audit history.

The adapter is still opt-in. SQLite local installations and IndexedDB browser
offline functionality are unchanged.
