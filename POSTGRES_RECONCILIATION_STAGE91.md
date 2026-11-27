# PostgreSQL reconciliation — Stage 91

- Source tables inventoried: **113**
- Explicit PostgreSQL CREATE TABLE coverage: **87**
- Remaining table DDL candidates: **26**
- Columns in remaining candidates: **346**
- Remaining foreign-key declarations: **33**
- Remaining indexes: **42**
- Live PostgreSQL catalog checked: **No**

Migration 162 adds the effective 15-column `school_ai_settings` table. The source definition originates in `migration_048_ai_layer`; the effective schema also includes the later nullable `tenant_id` column. AI feature defaults and privacy-related settings are retained.

These counts are static source reconciliation only. They do not establish that a live PostgreSQL database has the table or that all runtime SQL is PostgreSQL-compatible.
