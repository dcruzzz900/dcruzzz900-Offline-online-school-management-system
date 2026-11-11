# V105 — AI Module v0.2.0 Integration

Adapted to the supplied My School Hub v104 source rather than maintaining a standalone application.

## Changes
- Reused existing Flask app, authentication, CSRF, SQLite migration framework, school/tenant IDs, role checks, consent history and AI audit tables.
- Added additive migration `ai_v2_cbt_module` with AI feature flags and school/tenant-scoped CBT draft storage.
- Added Teacher Assistant, CBT Question Generator, Attendance Intelligence and Management Assistant routes/templates.
- Expanded AI privacy settings with per-school toggles for the new modules.
- Added OpenAI, Gemini and Anthropic provider adapters while retaining the legacy OpenAI-compatible API endpoint.
- Updated the AI Command Center to expose the eight approved AI modules.
- Added static integration-contract tests and `AI_V020_INTEGRATION.md`.

## Safety
- CBT output remains a draft; approval does not publish or insert it into a live CBT test.
- Attendance and management summaries are read-only.
- Existing result analysis/comment student-consent checks remain in place.
- No student records are sent by Teacher Assistant or CBT generation.

## Test limitations
Python compilation can be checked in this environment. Flask and pytest are not installed, and package-index access is unavailable; therefore the full runtime and v104 scenario suites remain unverified. Do not deploy to production until those tests pass on a machine with the requirements installed.
