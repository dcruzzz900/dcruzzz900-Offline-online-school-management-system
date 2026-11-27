# PostgreSQL-native table creation migrations

## Stage 27 — migration 100: `security_events`

The first explicitly reviewed table-creation migration is
`postgres_migration_100_security_events.py`. Its source definition was checked
against the final SQLite schema inventory in
`postgres_effective_schema_snapshot.json`.

`security_events` was selected because the audited definition is standalone
and has no foreign-key dependencies. The SQLite snapshot does include one
non-unique index (`idx_security_events_school_time`) and two append-only guards
(`trg_security_events_no_delete` and `trg_security_events_no_update`); all three
behaviours are included in this PostgreSQL migration. The PostgreSQL version
uses a `BIGINT` identity primary key and retains the application's existing
text timestamp column and UTC `YYYY-MM-DDTHH:MM:SSZ` default representation.
The immutable guards use a PostgreSQL trigger function that raises SQLSTATE
`55000` when an update or delete is attempted.

The migration is idempotent for a missing table and validates all expected
column names and PostgreSQL data types after `CREATE TABLE IF NOT EXISTS`.
The supporting index is created idempotently. The two triggers are replaced
idempotently so their append-only behaviour is present after the migration.
An existing incompatible table causes the migration to fail, allowing the
migration runner's transaction to roll back. It does not attempt to repair or
rewrite existing data.

The reviewed migration is registered in `postgres_migration_registry.py` and
can be applied with the standalone runner, for example:

```python
from postgres_migration_registry import POSTGRES_MIGRATIONS
from postgres_migrations import run_postgres_migrations

run_postgres_migrations(postgres_connection, POSTGRES_MIGRATIONS)
```

This registry is intentionally not imported by `db.py`; SQLite local startup
and browser IndexedDB offline behaviour remain unchanged. The migration has
been validated with unit-test fakes only. It has not been executed against a
live PostgreSQL server. Before production use, verify the DDL on the supported
PostgreSQL major version and review any deployment-specific schema/search-path
configuration.

This is one table migration, not a conversion of all 113 SQLite tables or the
99-entry SQLite migration registry. Tables with foreign keys, triggers,
indexes, table rebuilds, data backfills, or SQLite-specific constraints require
separate PostgreSQL-native migrations and dependency ordering.

## Stage 28 — migration 101: `platform_notifications`

Added `postgres_migration_101_platform_notifications.py`. This table is
created after the baseline `schools` table and therefore has an explicit
`BIGINT` foreign key from `school_id` to `schools.id`. The migration preserves
all six effective-schema columns, uses a `BIGINT` identity primary key, keeps
`read_at` and `created_at` as TEXT, and creates the reviewed descending
`created_at` index. It checks that `schools.id` exists as BIGINT before DDL,
then verifies the resulting column types, foreign-key target, and index shape.
Incompatible pre-existing objects fail closed; no rows are rewritten or
removed. The migration is registered as version 101 after version 100.

Validation is unit-test based. No live PostgreSQL server is available in this
environment, so DDL execution and FK/index catalog checks still require a real
PostgreSQL integration environment. The migration registry remains separate
from Flask's SQLite startup path.

## Stage 33 — migration 106: `ai_audit_log`

Added `postgres_migration_106_ai_audit_log.py` after reviewing the effective
SQLite schema snapshot and the source DDL in `db.py`. The table has 12 columns,
no declared foreign keys, one non-unique index (`idx_ai_audit_school_time` on
`school_id, created_at`), and one tenant-stamping trigger. The migration uses a
`BIGINT` identity primary key, maps the integer identifiers to `BIGINT`, and
preserves `created_at` as TEXT with its existing `CURRENT_TIMESTAMP` default.

The SQLite AFTER INSERT trigger fills a missing/empty tenant ID from
`schools.tenant_id`. Its PostgreSQL equivalent is a BEFORE INSERT trigger that
sets `NEW.tenant_id` directly, avoiding the SQLite rowid-based follow-up UPDATE.
This trigger depends on the baseline `schools` table being present when inserts
occur. The migration validates all 12 column names/types/nullability, the exact
primary/secondary index set, absence of foreign keys, and presence of the
PostgreSQL tenant-stamping trigger. It is registered as migration 106 and does
not connect the registry to SQLite startup.

Validation is unit-test based; no live PostgreSQL server was available for
execution of this DDL or trigger behaviour. Live PostgreSQL integration and
application-level database switching remain outstanding.


## Stage 34 — migration 107: `ai_outputs`

Added `postgres_migration_107_ai_outputs.py` after reviewing the effective SQLite schema snapshot and original table definition. The table has 15 columns, no declared foreign keys, two non-unique indexes (`idx_ai_outputs_school_feature` and `idx_ai_outputs_student`), a status CHECK constraint (`draft`, `approved`, `rejected`), and a tenant-stamping trigger. The PostgreSQL migration uses a BIGINT identity primary key, maps integer identifiers to BIGINT, preserves timestamp fields as TEXT, recreates both indexes, and ports tenant stamping as a BEFORE INSERT trigger. The migration validates the expected columns/types/nullability, exact index set, absence of foreign keys, and presence of the tenant trigger. It is registered as migration 107 and remains separate from SQLite startup. Validation is unit-test based; execution against a live PostgreSQL server remains outstanding.

## Stage 35 — migration 108: `announcement_dismissals`

Added `postgres_migration_108_announcement_dismissals.py` after reviewing the
`announcement_dismissals` definition in `postgres_effective_schema_snapshot.json`.
The source table has five columns, no declared foreign keys, no standalone
secondary indexes, and no triggers. Its SQLite auto-index represents the
composite UNIQUE constraint on `(announcement_id, actor_type, actor_id)`.
The PostgreSQL migration preserves that uniqueness as a named table constraint,
uses a BIGINT identity primary key, maps the two integer identifier columns to
BIGINT, and keeps `dismissed_at` as TEXT with the `CURRENT_TIMESTAMP` default.

The migration validates the column names/types/nullability, rejects unexpected
foreign keys, and verifies that the composite uniqueness index exists. It is
registered as migration 108 and remains isolated from SQLite startup. Tests
cover registration and the reviewed DDL contract; no live PostgreSQL server is
available here, so actual DDL execution and catalog validation remain pending.

## Stage 36 — migration 109: `announcements`

Added `postgres_migration_109_announcements.py` after reviewing the effective
SQLite schema snapshot and the original table definition. The source table has
14 columns, no declared foreign keys, one non-unique index
(`idx_announcements_school_expiry` on `(school_id, expires_at)`), and no
triggers. The migration uses a BIGINT identity primary key, maps SQLite
integer-valued fields and identifiers to BIGINT, and preserves all timestamp
fields as TEXT for application compatibility. The nullable `school_id`
continues to support platform-wide announcements. The migration validates the
column names/types/nullability, exact primary and secondary index set, absence
of foreign keys, and absence of triggers. It is registered as migration 109
and remains separate from SQLite startup. Unit tests and compilation validate
the migration definition; execution against a live PostgreSQL server remains
outstanding.

### Stage 37 — migration 110: `attendance_audit`

Reviewed against `postgres_effective_schema_snapshot.json`. Added the 19-column PostgreSQL table with a BIGINT identity primary key, TEXT timestamp compatibility, the source `subject_type` and `action` CHECK constraints, and `idx_attendance_audit_scope` on `(school_id, subject_type, attendance_date)`. The source has no declared foreign keys. Its append-only behavior is preserved with PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers that reject mutations. Migration 110 is registered in the standalone PostgreSQL registry; SQLite startup remains unchanged.

## Stage 37 — migration 110: `attendance_audit`

Added `postgres_migration_110_attendance_audit.py` after reviewing the
`attendance_audit` definition in the effective SQLite schema snapshot. The
migration preserves all 19 columns, both source CHECK constraints, and the
`idx_attendance_audit_scope` index. It ports the append-only history behavior
with PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers. Timestamp values
remain TEXT. The migration is registered as version 110 and remains separate
from SQLite startup. Unit tests validate the DDL contract and registry; live
PostgreSQL execution remains pending.

## Stage 38 — migration 111: `billing_job_runs`

Added `postgres_migration_111_billing_job_runs.py` after reviewing the exact
`billing_job_runs` definition and index declarations in the effective SQLite
schema snapshot. The source table has seven columns, no foreign keys, no
triggers, and two non-unique indexes: `idx_billing_job_runs_status` on
`status`, and `idx_billing_job_runs_name_started` on `(job_name, started_at)`.
The PostgreSQL migration uses a BIGINT identity primary key, preserves the
TEXT timestamp and JSON payload fields, and retains the source defaults for
`started_at` and `status`. It validates the column shape, absence of foreign
keys/triggers, and exact index definitions. It is registered as migration 111
and is not connected to SQLite startup. Live PostgreSQL execution remains
outstanding.

## Stage 39 — migration 112: `billing_email_delivery`

Added `postgres_migration_112_billing_email_delivery.py` after reviewing the
exact table definition and indexes in `postgres_effective_schema_snapshot.json`.
The table has 12 columns, one foreign key from `school_id` to the baseline
`schools.id`, a school-scoped unique constraint on `(school_id, event_key)`,
and two non-unique indexes (`idx_billing_email_status` and
`idx_billing_email_school`). The baseline defines `schools.id` as PostgreSQL
INTEGER, so the migration deliberately uses INTEGER for `school_id` to keep
foreign-key types compatible; the table's own generated primary key is BIGINT.
Timestamp fields remain TEXT and source defaults are preserved. The migration
validates the school key type, column types/nullability, exact foreign key,
index set, and absence of triggers. It is registered as migration 112 and
remains separate from SQLite startup. Live PostgreSQL execution remains
outstanding.

## Stage 40 — migration 113: `billing_invoices`

Added `postgres_migration_113_billing_invoices.py` after reviewing the exact
`billing_invoices` definition and index declarations in
`postgres_effective_schema_snapshot.json`. The table has 13 columns, one
foreign key from `school_id` to baseline `schools.id`, globally unique
`invoice_number`, and two non-unique indexes (`idx_billing_invoices_status`
and `idx_billing_invoices_school`). The baseline defines `schools.id` as
PostgreSQL INTEGER, so `school_id` remains INTEGER; the new table's generated
primary key is BIGINT. SQLite REAL is mapped to PostgreSQL DOUBLE PRECISION,
while timestamp-like fields remain TEXT and source defaults are retained.
The migration validates the baseline key type, column shape, foreign key,
index set, and absence of triggers. It is registered as migration 113 and
remains separate from SQLite startup. Live PostgreSQL execution remains
outstanding.


## Stage 40 — Migration 113: `billing_invoices`

- Ported the reviewed 13-column `billing_invoices` table.
- Preserved the globally unique invoice number, school foreign key, defaults, and status/school indexes.
- Kept timestamp fields as TEXT and mapped `amount_ngn` to DOUBLE PRECISION.
- Added schema, foreign-key, index, and trigger validation.

## Stage 41 — Migration 114: `billing_notification_events`

- Ported the reviewed five-column `billing_notification_events` table.
- Preserved the `(school_id, event_key)` uniqueness rule and the school foreign key.
- Recreated `idx_billing_notification_type` and `idx_billing_notification_school`.
- Kept `created_at` as TEXT with its `CURRENT_TIMESTAMP` default.
- Added schema, foreign-key, index, and trigger validation.

## Stage 42 — Migration 115: `billing_payments`

- Ported the reviewed 13-column `billing_payments` table.
- Preserved source defaults, nullable fields, and TEXT timestamp/metadata representation.
- Mapped SQLite `REAL` amount values to PostgreSQL `DOUBLE PRECISION`.
- Added the school foreign key to baseline `schools(id)` (`INTEGER`) and invoice foreign key to migration 113 `billing_invoices(id)` (`BIGINT`).
- Preserved the unique `idx_billing_payments_reference` index and the status/school lookup indexes.
- Added catalog validation for dependency key types, columns, foreign keys, indexes, and unexpected triggers.
- Registered migration 115; PostgreSQL migrations remain separate from SQLite startup.

## Stage 43 — Migration 116: `billing_payment_history`

- Ported the reviewed 13-column `billing_payment_history` table.
- Preserved foreign keys to `billing_payments(id)`, baseline `schools(id)`, and `billing_invoices(id)` with matching PostgreSQL key types.
- Mapped the two SQLite REAL amount-history columns to PostgreSQL DOUBLE PRECISION; timestamp values remain TEXT.
- Recreated the payment/created-at and school/created-at lookup indexes.
- Ported the source append-only behavior with PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers that reject mutation using the source error message.
- Added validation for dependency key types, columns, foreign keys, indexes, and both immutable-history triggers.
- Registered migration 116. PostgreSQL migrations remain separate from SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 44 — Migration 117: `billing_adjustments`

- Ported the reviewed 18-column `billing_adjustments` table from the effective SQLite schema snapshot.
- Preserved the unique `reference` constraint and the `status` and `payment_id` lookup indexes.
- Added foreign keys to baseline `schools(id)` (`INTEGER`), migration 115 `billing_payments(id)` (`BIGINT`), and migration 113 `billing_invoices(id)` (`BIGINT`).
- Mapped SQLite `REAL` amount values to PostgreSQL `DOUBLE PRECISION`; timestamp fields remain TEXT and source defaults are retained.
- Added validation for dependency key types, columns/nullability, exact foreign keys, indexes, and absence of triggers.
- Registered migration 117. It remains separate from SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 45 — Migration 118: `billing_financial_audit`

- Ported the reviewed 10-column `billing_financial_audit` table from the effective SQLite schema snapshot.
- Preserved optional foreign keys to baseline `schools(id)` (`INTEGER`), migration `billing_payments(id)` (`BIGINT`), and migration `billing_invoices(id)` (`BIGINT`).
- Recreated four source lookup indexes for invoice, payment, school, and creation time.
- Ported the source immutable-audit behavior using PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers with the original error message.
- Preserved `created_at` as TEXT with its `CURRENT_TIMESTAMP` default.
- Added dependency-key, column/nullability, foreign-key, exact-index, and trigger validation.
- Registered migration 118. It remains separate from SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 46 — Migration 119: `billing_receipts`

- Ported the reviewed 10-column `billing_receipts` table from the effective SQLite schema snapshot.
- Preserved unique `payment_id` and `receipt_number` constraints and the invoice/school lookup indexes.
- Added foreign keys to baseline `schools(id)` (`INTEGER`), migration `billing_invoices(id)` (`BIGINT`), and migration `billing_payments(id)` (`BIGINT`).
- Mapped SQLite `REAL` amount values to PostgreSQL `DOUBLE PRECISION`; kept `issued_at` as TEXT and preserved source defaults.
- Added dependency-key, column/nullability, foreign-key, exact-index, and absence-of-trigger validation.
- Registered migration 119. It remains separate from SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 47 — Migration 120: `billing_reconciliation_exceptions`

- Ported all 12 columns from the reviewed effective SQLite schema snapshot.
- Added nullable BIGINT foreign keys to `billing_payments(id)` and `billing_invoices(id)` after validating both dependency key types.
- Preserved the unique `exception_key` constraint and the three lookup indexes for invoice, payment, and status.
- Preserved source defaults, including empty `details`, `open` status, and `created_at` as TEXT with `CURRENT_TIMESTAMP` default.
- Added validation for columns, nullability, dependency types, foreign keys, unique/index definitions, and absence of source triggers.
- Registered migration version 120; PostgreSQL migrations remain standalone and are not connected to SQLite startup.

## Stage 48 — Migration 121: `billing_renewal_recovery`

- Ported the nine columns from the reviewed effective SQLite schema.
- Preserved the invoice/school foreign keys, including the source-compatible key types (`billing_invoices.id` BIGINT and baseline `schools.id` INTEGER).
- Preserved uniqueness across `(invoice_id, attempt_no)` and the `(status, next_attempt_at)` scheduling index.
- Kept timestamp and scheduling values as TEXT for application compatibility and retained source defaults.
- Added validation for dependency key types, columns/nullability, foreign keys, indexes, and unexpected triggers.
- This migration remains standalone and is not connected to SQLite startup.

## Stage 49 — Migration 122: `billing_report_downloads`

- Ported the nine-column `billing_report_downloads` table from the effective SQLite schema snapshot.
- Preserved `actor_type`, optional actor/date fields, report metadata, `row_count` defaulting to zero, and `created_at` as TEXT with its `CURRENT_TIMESTAMP` default.
- Recreated `idx_billing_report_downloads_created` on `created_at`.
- Ported the source immutable-record behavior using PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers with the source error message.
- Confirmed the source declares no foreign keys; validation rejects unexpected foreign keys and checks the exact column, index, and trigger sets.
- Registered migration 122. It remains standalone and is not connected to SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 50 — Migration 123: `billing_webhook_events`

Reviewed the effective SQLite schema snapshot and ported `billing_webhook_events` as a standalone PostgreSQL migration. The migration preserves all 10 columns, the `received` status default, `CURRENT_TIMESTAMP` received-time default, the non-unique payment-reference index, and the unique `(provider, provider_event_id)` idempotency index. The source declares no foreign keys or triggers; validation checks that neither is unexpectedly present. The integer primary key is represented as a BIGINT identity. This migration is registered but is not connected to SQLite startup.

## Stage 51 — Migration 124: `change_audit`

- Ported all 16 columns from the reviewed effective SQLite schema snapshot.
- Added the required `school_id` foreign key to baseline `schools(id)` using the matching PostgreSQL `INTEGER` key type; retained `user_id` and `server_id` as nullable INTEGER fields because the source declares no foreign keys for them.
- Preserved `server_ts` as TEXT with its `CURRENT_TIMESTAMP` default.
- Recreated the conditional unique idempotency index on `(school_id, change_id)` only when `change_id` is present and the outcome is `applied`, `merged`, or `latest_wins`.
- Recreated the `(school_id, entity, client_uuid)` and `(school_id, id)` lookup indexes.
- Added validation for all columns/nullability, the exact school foreign key, exact index set and partial-index predicate, and absence of triggers.
- Registered migration 124. It remains standalone and is not connected to SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 52 — migration 125: `class_login_codes`

Added `postgres_migration_125_class_login_codes.py` after reviewing the effective SQLite schema snapshot. The source table has 15 columns, no declared foreign keys or triggers, a four-value status CHECK constraint, and three explicit indexes: a school/class lookup index, a unique code index, and a partial unique index allowing only one active code per class. The PostgreSQL migration uses a BIGINT identity primary key, maps SQLite INTEGER columns to BIGINT, preserves timestamp fields as TEXT and source defaults, recreates the CHECK constraint and all three indexes, and validates the resulting columns, nullability, foreign-key absence, exact index definitions, CHECK values, and trigger absence. It is registered as migration 125 and remains separate from SQLite startup. Live PostgreSQL execution remains outstanding.

## Stage 53 — Migration 126: `custom_field_options`

- Ported all seven columns from the reviewed effective SQLite schema snapshot.
- Preserved the composite uniqueness rule on `(field_id, option_value)` and the `display_order` / `is_active` defaults (`0` and `1`).
- Represented the SQLite integer primary key as a PostgreSQL BIGINT identity and other SQLite INTEGER fields as BIGINT.
- Confirmed the source declares no foreign keys, secondary indexes, or triggers; validation rejects unexpected foreign keys/triggers and checks the exact index set.
- Registered migration 126. It remains standalone and is not connected to SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 54 — Migration 127: `class_subject_requirements_v2`

- Ported all 18 columns from the reviewed effective SQLite schema snapshot.
- Preserved the scoped unique key on `(tenant_id, school_id, class_id, subject_id)` and the partial unique `client_uuid` index.
- Added foreign keys to baseline `schools(id)`, `classes(id)`, and `subjects(id)`. Their referenced keys are PostgreSQL `INTEGER`, so the corresponding foreign-key columns remain `INTEGER`; the independent row ID and non-FK SQLite integer fields use `BIGINT`.
- Preserved scheduling defaults, status default, and TEXT timestamp/client UUID fields.
- Reimplemented the source insert-time UUID/timestamp defaults and monotonic update timestamp behavior with PostgreSQL BEFORE INSERT/UPDATE triggers. UUID values are 32-character lowercase hexadecimal strings, matching the source's `lower(hex(randomblob(16)))` representation.
- Added validation for dependency key types, all columns/nullability, exact foreign keys, exact indexes/partial predicate, and both sync triggers.
- Registered migration 127. It remains standalone and is not connected to SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 55 — Migration 128: `class_timetable_preferences_v2`

Reviewed the effective SQLite schema snapshot and ported all 15 columns, the `schools` and `classes` foreign keys, the partial unique client UUID index, and both synchronization triggers. `school_id` and `class_id` remain PostgreSQL INTEGER to match their baseline referenced keys; other SQLite integer values use BIGINT. The migration remains standalone and does not alter SQLite startup or offline synchronization. See `V128_IMPLEMENTATION_NOTES.md`.

## Stage 56 — Migration 129: `custom_fields`

- Ported all 21 columns from the effective SQLite schema snapshot.
- Preserved the `applies_to` CHECK constraint (`student` or `staff`) and the unique `(school_id, applies_to, field_key)` constraint.
- Recreated `idx_custom_fields_scope` and the partial, case-insensitive unique index `ux_custom_fields_label` on `(school_id, applies_to, LOWER(label))` for non-archived fields.
- Kept `school_id` as INTEGER to match the baseline school identifier type; generated row IDs and other SQLite integer fields use BIGINT.
- The source declares no foreign keys or triggers; none were added.
- This migration is registered in the standalone PostgreSQL runner and is not imported by SQLite startup.

## Stage 57 — migration 130: `custom_field_values`

Added `postgres_migration_130_custom_field_values.py` after reviewing the
`custom_field_values` table definition and its index entries in the effective
SQLite schema snapshot. The source has ten columns, an `entity_type` CHECK
constraint limited to `student` and `staff`, a composite UNIQUE constraint on
`(field_id, entity_id)`, a non-unique lookup index on
`(school_id, entity_type, entity_id)`, and a partial unique index on
`(field_id, unique_value)` where `unique_value` is not NULL. It declares no
foreign keys or triggers; none are introduced. The migration preserves
`updated_at` as TEXT with its `CURRENT_TIMESTAMP` default and uses BIGINT
identifiers with a BIGINT identity primary key.

The migration validates column types/nullability, both table constraints,
the exact index set and index definitions, and the absence of foreign keys
and triggers. It is registered as version 130 and remains separate from
SQLite startup and the existing offline-sync path. Validation is unit-test
based; execution against a live PostgreSQL server remains outstanding.

## Stage 58 — Migration 131: `deferred_actions`

- Ported all 12 columns from the reviewed effective SQLite schema snapshot.
- Preserved the `school_id` foreign key to baseline `schools(id)` using PostgreSQL INTEGER for key compatibility; `user_id` remains a nullable BIGINT because the source declares no user foreign key.
- Preserved the unique `client_uuid` constraint and `idx_deferred_actions_school` lookup index.
- Preserved `status` defaulting to `pending` and `created_at` as TEXT with its `CURRENT_TIMESTAMP` default.
- Confirmed the source declares no triggers; validation rejects unexpected triggers and checks the exact columns, constraints, foreign key, and index set.
- Registered migration 131. It remains standalone and is not connected to SQLite startup; live PostgreSQL execution remains outstanding.

## Stage 59 — Migration 132: `device_credentials`

- Ported all 14 columns from the reviewed effective SQLite schema snapshot.
- Preserved `device_id` uniqueness and the three tenant, school, and user lookup indexes.
- Added foreign keys to baseline `schools(id)` and `users(id)`. Both referenced identifiers are PostgreSQL `INTEGER`, so `school_id` and `user_id` remain `INTEGER`; the independent row identifier is a BIGINT identity.
- Preserved `issued_at` as TEXT with its `CURRENT_TIMESTAMP` default, nullable tenant/device metadata, and the `revoked` default of `0`.
- Reimplemented the source AFTER INSERT tenant-stamping trigger: when `tenant_id` is NULL or empty, it is populated from the matching school's tenant ID.
- Added validation for dependency key types, columns/nullability, exact constraints and foreign keys, index set/columns, and trigger presence.
- Registered migration 132. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.

## Stage 60 — Migration 133: `offline_sync_tokens`

- Ported all four columns from the reviewed effective SQLite schema snapshot.
- Preserved `token` as the text primary key, `entity_type` as required TEXT, `entity_id` as BIGINT, and `created_at` as TEXT with its `CURRENT_TIMESTAMP` default.
- Preserved the source's absence of foreign keys, secondary indexes, and triggers; no relationships or synchronization side effects were invented.
- Added validation for the exact column set/types/nullability, primary-key constraint/index, and absence of foreign keys and triggers.
- Registered migration 133 in the standalone PostgreSQL migration runner. It does not connect this table to SQLite startup or alter the existing offline-sync implementation. Live PostgreSQL execution remains outstanding.

## Stage 61 — Migration 134: `fixed_activities_v2`

- Ported the 18-column `fixed_activities_v2` table from the effective SQLite schema snapshot.
- Preserved the `schools(id)` foreign key, the partial unique `client_uuid` index, and source defaults (`is_mandatory=1`, `is_immovable=1`, `is_deleted=0`).
- Reimplemented SQLite sync-default and monotonic timestamp-touch behaviour with PostgreSQL BEFORE INSERT/UPDATE triggers. Generated timestamps retain the source ISO-like TEXT representation.
- Validates exact column names/types/nullability, the school key type and FK, expected indexes, and both triggers.
- Registered migration version 134. This remains standalone and is not imported by SQLite startup; live PostgreSQL execution has not been performed in this stage.

## Stage 62 — Migration 135: `grading_config_audit`

- Ported all 15 columns from the reviewed effective SQLite schema snapshot.
- Preserved the foreign key from `school_id` to baseline `schools(id)`; `school_id` remains PostgreSQL INTEGER to match the referenced key.
- Mapped the eight SQLite REAL score-limit columns to PostgreSQL DOUBLE PRECISION, the generated row identifier and other SQLite INTEGER fields to BIGINT, and retained `changed_at` as TEXT with its `CURRENT_TIMESTAMP` default.
- Preserved `affected_count` as NOT NULL with default `0` and recreated `idx_grading_config_audit_school` on `(school_id, changed_at)`.
- The source declares no triggers; validation rejects unexpected triggers and checks the exact column set, nullability, foreign key, and index set/definition.
- Registered migration 135. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.

## Stage 63 — Migration 136: `parent_accounts`

- Ported all 16 columns from the effective SQLite schema snapshot.
- Preserved the foreign key from `school_id` to baseline `schools(id)` using PostgreSQL INTEGER for key compatibility; the generated parent-account ID and other SQLite INTEGER fields use BIGINT.
- Preserved the unique `(school_id, username)` constraint.
- Preserved defaults for `is_active`, `last_notification_seen_id`, `created_at`, `account_status`, and `signup_status`; date-of-birth, gender, contact and photo fields remain nullable as in the source.
- Reimplemented the source AFTER INSERT tenant-stamping trigger for empty `tenant_id` values, looking up the tenant from the matching school. The source schema declares `tenant_id NOT NULL` while its trigger also checks for NULL; PostgreSQL therefore preserves the meaningful empty-string path and documents this source inconsistency rather than weakening the column constraint.
- Added validation for exact columns/nullability, the school key type and foreign key, primary/unique index definitions, and the tenant-stamping trigger.
- Registered migration 136. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.

## Stage 64 — Migration 137: `parent_consent_events`

- Ported all eight columns from the effective SQLite schema snapshot.
- Preserved the `action` CHECK constraint (`granted` or `withdrawn`), nullable `policy_version` and `tenant_id`, and `created_at` TEXT default.
- Added foreign keys to `schools`, `students`, and `parent_accounts`; school/student identifiers remain INTEGER and the parent identifier is BIGINT to match the referenced PostgreSQL keys.
- Reimplemented the source AFTER INSERT tenant-stamping trigger, filling a NULL or empty tenant ID from the associated school.
- The source declares no secondary indexes; no additional indexes were introduced.
- Added validation for dependency key types, exact columns/nullability, foreign keys, CHECK constraint, primary-key index, and tenant trigger.
- Registered migration 137. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.

## Stage 65 — Migration 138: `parent_students`

- Ported all ten columns from the effective SQLite schema snapshot.
- Preserved the required school, student, and parent-account relationships. `school_id` and `student_id` remain PostgreSQL INTEGER; `parent_id` is BIGINT to match `parent_accounts.id`. The generated row ID and non-FK `verified_by` use BIGINT.
- Preserved `ON DELETE CASCADE` for parent-account and student references, and the source's non-cascading school reference.
- Preserved unique `(parent_id, student_id)`, plus `idx_parent_students_parent(parent_id, school_id)` and `idx_parent_students_student(student_id, school_id)`.
- Preserved `status='pending'`, nullable verification/revocation fields, and `created_at` as TEXT with `CURRENT_TIMESTAMP` default.
- Reimplemented the source AFTER INSERT tenant-stamping trigger. Because `tenant_id` is declared NOT NULL in the source, the empty-string condition is the effective stamping path; the source NULL check is retained in the PostgreSQL function.
- Added validation for dependency key types, exact columns/nullability, foreign keys, indexes, and trigger presence. Registered migration 138; it remains standalone and does not alter SQLite startup or offline synchronization. Live PostgreSQL execution remains outstanding.

## Stage 66 — migration 139: `parent_teacher_messages`

Added `postgres_migration_139_parent_teacher_messages.py` after reviewing the
source table and its indexes/triggers in `postgres_effective_schema_snapshot.json`.
The migration preserves all ten columns, the sender-type CHECK constraint, the
four declared foreign keys (including `ON DELETE CASCADE` for `parent_accounts`),
and both message lookup indexes. Identifier types match the referenced
PostgreSQL keys: `parent_id` is BIGINT while school, teacher, and student IDs
remain INTEGER. The source AFTER INSERT tenant-stamping trigger is recreated.
The migration is registered as version 139 and remains isolated from SQLite
startup. Automated tests validate the DDL contract and catalog checks; live
PostgreSQL execution remains outstanding.

## Stage 67 — Migration 140: `password_reset_tokens`

- Ported all seven columns from `password_reset_tokens` in the effective SQLite schema snapshot.
- Preserved the required `account_type` CHECK restriction (`staff` or `parent`), unique `token_hash`, and the account lookup index on `(account_type, account_id)`.
- Preserved `created_at` as required TEXT with `CURRENT_TIMESTAMP`, required `expires_at`, and nullable `used_at`.
- Kept `account_id` as a polymorphic identifier with no foreign key, matching the source schema; the account type determines whether it refers to a staff or parent account.
- Added validation for exact columns/nullability, primary/unique/check constraints, index definitions, and the absence of foreign keys and triggers.
- Registered migration 140. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.

## Stage 68 — Migration 141: `platform_activation_requests`

- Ported all nine columns from `platform_activation_requests` in the reviewed effective SQLite schema snapshot.
- Preserved the required `school_id` relationship to baseline `schools(id)` using PostgreSQL INTEGER to match the referenced key; the generated request ID is a BIGINT identity.
- Preserved `status` as required TEXT with default `pending`, `submitted_at` as nullable TEXT with `CURRENT_TIMESTAMP`, and all nullable approval and activation-code delivery metadata.
- Recreated `idx_platform_activation_requests_status` on `(status, submitted_at)`.
- The source declares no CHECK constraints, additional unique constraints, or triggers; validation checks the exact columns, primary/foreign-key constraints, index definition, and absence of triggers.
- Registered migration 141. It remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.

## Stage 69 — Migration 142: `rbac_audit_log`

- Ported all 13 columns from the reviewed effective SQLite schema snapshot. The generated record ID and polymorphic actor ID use BIGINT; `school_id` remains INTEGER to match the baseline `schools(id)` key type.
- Preserved `action` as required TEXT and `created_at` as nullable TEXT with the source `CURRENT_TIMESTAMP` default.
- Recreated `idx_rbac_audit_school` on `(school_id, created_at)`.
- Recreated the source append-only protections: UPDATE and DELETE are rejected with the audit-history message. The source declares no foreign keys or additional constraints.
- Added validation for exact columns/nullability, the primary key, index definition, and both append-only triggers. Registered migration 142.
- The migration remains standalone and is not connected to SQLite startup or the existing offline-sync path. Live PostgreSQL execution remains outstanding.


## Stage 70 — Migration 143: `role_assignment_audit`

- Ported all 14 columns from the effective schema snapshot; school ID remains INTEGER, other identifiers are BIGINT.
- Recreated `idx_role_assignment_audit_school` on `(school_id)`.
- Recreated append-only UPDATE/DELETE protections using the shared immutable-row trigger.
- Added validation for exact column definitions, primary key, index and trigger set; registered migration 143.
- Standalone PostgreSQL migration; SQLite startup/offline sync remain unchanged. Live PostgreSQL execution remains outstanding.

## Stage 71 — Migration 144: `role_assignments`

Added standalone PostgreSQL migration `postgres_migration_144_role_assignments.py`. The migration recreates the 20-column effective schema, school-level and status checks, references to the existing `users` and `schools` tables, and six lookup indexes. It validates the expected columns and indexes and is registered in the standalone registry. It expects the referenced tables to exist with compatible key types. It does not alter SQLite startup or offline synchronization. Unit/contract tests only; live PostgreSQL execution remains untested.

## Stage 74 — migration 147: `score_audit`

Added standalone PostgreSQL migration 147 for the 33-column `score_audit` table from the effective SQLite schema in `db.py`. Preserves the school/term/class/subject composite lookup index and school/student lookup index. Score values use PostgreSQL `DOUBLE PRECISION`; identifiers use `BIGINT`; `changed_at` remains TEXT with the source `CURRENT_TIMESTAMP` default. Adds BEFORE UPDATE and BEFORE DELETE protections using the existing `app_reject_immutable_row` helper. Schema, primary-key, index, and trigger validation plus migration-specific tests are included. This migration is registered only in the standalone PostgreSQL registry; SQLite startup and offline synchronization are unchanged. Live PostgreSQL execution remains untested.

## Stage 76 — Migration 149: `result_publication`

Added standalone PostgreSQL migration 149 for the 17-column `result_publication` workflow-state table defined in `db.py` within `migration_062_v63_spec`. Preserves the seven allowed workflow statuses and the unique `(school_id, class_id, term_id)` constraint. Includes column, constraint, and index validation plus migration-specific tests. Registered only in `postgres_migration_registry.py`; SQLite startup and offline synchronization remain unchanged. Live PostgreSQL execution remains untested.

## Migration 150 — `result_publication_audit`

Ports the result publication workflow audit history table from the SQLite schema into the standalone PostgreSQL registry. Includes its scope index and append-only protections. This migration is not invoked by SQLite startup and does not change offline synchronization.
