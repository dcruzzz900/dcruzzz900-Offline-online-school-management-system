# My School Hub AI v0.2.0 — integration notes

## Baseline and integration approach

This release is adapted directly to the supplied `school-result-system-v104.zip` application. It is **not** a second Flask app and does not create a parallel users/schools/students database. It reuses:

- `app.py` Flask application, existing login session, `login_required`, CSRF protection and current-school/current-tenant helpers.
- `db.py` SQLite connection and named, additive migration framework.
- Existing `schools`, `users`, `students`, `classes`, `subjects`, `terms`, `scores`, `attendance_records`, `school_ai_settings`, `student_ai_consent`, `ai_outputs` and `ai_audit_log` tables.
- Existing class assignment / result-access checks for teachers.

The new migration is named `ai_v2_cbt_module`. It adds feature switches to `school_ai_settings` and creates `ai_cbt_sets` and `ai_usage_monthly`. Existing data is not deleted or rebuilt. School and tenant identity are taken from the authenticated session and database; request form values are never accepted as tenant identifiers.

## Eight approved AI modules

| Module | v104 integration | v0.2.0 status |
|---|---|---|
| Student Tutor | Existing `/student/ai-tutor` and `ai_tutor` switch | Existing; retained |
| Teacher Assistant | New `/ai/teacher-assistant` | Added; provider-backed with local draft fallback |
| CBT Question Generator | New `/ai/cbt-generator` | Added; creates tenant-scoped draft sets and review screen |
| Academic Performance Analyst | Existing `/ai/result-analysis` and `/ai/analyze` | Existing; retained with consent gate |
| Result Comment Generator | Existing `/ai/comments` and review workflow | Existing; retained with consent gate |
| Learning Material Assistant | Existing `/ai/learning-materials` | Existing; retained |
| Attendance Intelligence | New `/ai/attendance-intelligence` | Added; read-only class summaries |
| Management Assistant | New `/ai/management-assistant` | Added; read-only operational indicators |

Existing performance alerts and result assistant remain available as supporting tools.

## CBT safety boundary

Generated questions are stored only in `ai_cbt_sets` as drafts. Review/approval updates the draft's review status only. This version does **not** publish a CBT exam, create a live test, or insert questions into a live CBT question bank. Teachers must validate wording, syllabus alignment, answer keys and explanations before any later integration with the shared CBT portal. The local fallback questions are deliberately marked for validation and should not be treated as finished exam content.

## Multi-provider configuration

Set credentials as server environment variables only; never place them in templates, browser JavaScript, ZIP source, or database rows.

- OpenAI: `AI_PROVIDER=openai`, `OPENAI_API_KEY=...`, optional `OPENAI_BASE_URL` and `AI_MODEL` (default `gpt-4o-mini`).
- Gemini: `AI_PROVIDER=gemini`, `GEMINI_API_KEY=...`, optional `GEMINI_MODEL` (default `gemini-2.0-flash`).
- Anthropic: `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...`, optional `ANTHROPIC_MODEL` and `ANTHROPIC_API_URL`.
- Legacy OpenAI-compatible endpoint: `AI_API_URL=...`, `AI_API_KEY=...`, optional `AI_MODEL=...`; this remains supported.
- `AI_PROVIDER=auto` (default) selects the first configured supported provider.

The application does not make a provider request unless the relevant route invokes the adapter. AI credentials remain server-side. No live provider request was made during this build.

## Role and tenant access

- School Admin/Sub-Admin: school AI settings and management assistant.
- School Admin/Sub-Admin/Teacher: teacher assistant, CBT draft generation/review, attendance intelligence and existing staff AI tools.
- Teacher class selection and CBT draft viewing are constrained by existing assigned-class/result-access helpers.
- Student Tutor continues to use the existing student login session.
- CBT reads and writes require both `school_id` and `tenant_id`; both values come from the authenticated session.
- Platform Super Admin remains a separate platform-admin identity in v104. This version does not grant platform admins school-user sessions or expose school-level student data to them.

## Privacy and data handling

- Identifiable result analysis and result comments continue to require AI enabled, student-data processing enabled, and recorded student consent.
- Teacher Assistant receives only the teacher's submitted prompt, not student records.
- CBT generation receives subject/class/topic/difficulty/count, not student records.
- Attendance Intelligence and Management Assistant are deterministic, read-only database summaries; they do not send student-level attendance records to a model.
- Outputs are drafts. AI never edits scores, grades, attendance, promotion, published results or live exams.

## Verification status and remaining work

Completed in this source package:

- Source inspected against v104's actual Flask app, SQLite migration framework, auth decorators, session identity and tenant model.
- Additive schema migration and new routes/templates added.
- Multi-provider adapters added while preserving legacy provider configuration.
- Python syntax compilation and static AI v0.2.0 contract checks are intended to run locally.

Not certified in this build environment:

- Full Flask application startup, pytest suites, browser rendering and live provider calls. The build environment does not have Flask installed and has no package-index network access, so runtime integration tests could not be executed here.
- Full v104 regression suite (75+ scenario checks) has not been run.
- CBT live exam integration is intentionally not implemented yet. This is a draft generator only.
- Monthly budget enforcement, detailed token/cost metering, provider selection UI, R2 attachments, offline AI request queue, and Neon PostgreSQL runtime compatibility are not implemented in this release.

**Deployment instruction:** do not replace the live Render deployment with this ZIP yet. First run the local tests in the included instructions, back up the current database, then stage on a separate test deployment. The app is still using v104's SQLite database layer; this release does not migrate it to Neon.

## Local verification commands

On a machine with Python and network access to install dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m compileall -q app.py db.py ai
pytest -q tests/test_ai_v020_contract.py
python tests/v104_scenarios.py
```

Run the app locally only after making a separate copy of any existing database. For a clean test instance, set `DATA_DIR` to a new temporary folder and leave `SKIP_DEMO_SEED` unset if you want demo data; never point a test run at the live Render data directory.
