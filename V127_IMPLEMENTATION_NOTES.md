# Migration 127 — class_subject_requirements_v2

Source: `postgres_effective_schema_snapshot.json` in the Stage 53 archive.

The source table contains 18 columns, a four-column unique constraint, three foreign keys (school, class, subject), a partial unique index on non-null `client_uuid`, and two SQLite AFTER triggers for insert defaults and update timestamp touching.

The PostgreSQL implementation uses a BIGINT identity primary key. `school_id`, `class_id`, and `subject_id` are INTEGER to match the existing baseline keys. Other SQLite INTEGER fields are BIGINT. Timestamp values remain TEXT for application compatibility.

The source AFTER triggers are represented by two PostgreSQL BEFORE triggers using one PL/pgSQL function. On insert, missing client UUIDs are filled with a 32-character lowercase hexadecimal MD5 value and missing `updated_at` values receive a UTC ISO-like timestamp. On update, if the caller leaves `updated_at` unchanged, it advances to the current UTC second or one second after the previous timestamp to retain monotonic behavior.

The migration validates the referenced baseline key types, columns and nullability, exact foreign-key set, exact index set and partial-index predicate, and exact trigger names. It is registered as migration 127 but is not imported by SQLite startup. No live PostgreSQL server was available for execution testing.
