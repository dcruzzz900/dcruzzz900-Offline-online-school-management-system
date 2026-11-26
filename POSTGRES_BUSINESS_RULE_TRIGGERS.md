# PostgreSQL business-rule trigger port

This artifact ports the two remaining SQLite triggers classified as `business_rule_or_other`.

- `trg_schools_school_code_permanent`: a non-empty existing school code cannot be changed. NULL and empty legacy values may be initialized, and assigning the same value remains valid. `IS DISTINCT FROM` preserves SQLite's NULL-aware `IS NOT` comparison. The trigger is restricted to updates naming `school_code`.
- `trg_users_signup_name_init`: after inserting a user, initialize `signup_name` from `name` only when the inserted value is NULL or the empty string. This deliberately remains an AFTER INSERT trigger and performs its update in the same transaction, matching the source trigger's timing and rollback behavior.

The signup-name initialization update must be installed alongside the Stage 16 `signup_name` immutability trigger. Its empty-to-initial-value transition is allowed by that guard; subsequent changes remain blocked.

## Generate

```bash
python tools/build_postgres_business_rule_triggers.py
```

The generator validates the exact source trigger inventory, expected SQL fragments, and effective-schema columns. It fails closed on drift. The generated SQL is opt-in and is not applied automatically.

## Deployment checks

Apply to a disposable PostgreSQL database first. Verify that a populated `school_code` cannot be changed, a NULL/empty legacy code can be initialized, unchanged values are accepted, and unrelated updates are unaffected. Verify that inserted users with NULL/empty `signup_name` receive `name`, explicit non-empty values are retained, and a later attempt to change a non-empty signup name is rejected. Test multi-row inserts and transaction rollback.

The school-code exception uses SQLSTATE `P0001` and the original user-facing message. Confirm the application's exception mapping and API response handling before deployment. No live PostgreSQL server was available during generation, so PostgreSQL execution and integration tests remain outstanding.
