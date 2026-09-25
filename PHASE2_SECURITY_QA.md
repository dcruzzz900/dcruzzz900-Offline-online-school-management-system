# Phase 2 Security & QA Notes

## Parent/Teacher messaging checks

The messaging implementation is scoped by `school_id` plus the authenticated parent/teacher identity.

- Parent conversations require an active parent session and a child linked through `parent_students`.
- Parent recipients can only open teachers responsible for the selected child's class/form.
- Teacher threads require the authenticated teacher to match `conversation.teacher_id` and the current school.
- Parent replies create recipient-specific teacher notifications.
- Teacher replies create recipient-specific parent notifications.
- Message bodies are limited to 4,000 characters.
- POST forms include the application's CSRF token.
- Message display uses Jinja autoescaping.

## Verification performed in this environment

- Python `compileall`: passed.
- Existing static `security_audit.py`: passed with no reported findings.
- Project archive integrity: passed.

## Runtime verification limitation

The execution environment has no network access, so project dependencies cannot be downloaded. A clean runtime test suite requiring Flask therefore could not be executed here.

Before production deployment, run:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

Then manually verify the end-to-end flow:

1. Admin creates/activates a parent account.
2. Parent signs in and selects a child.
3. Parent opens Contact Teacher.
4. Parent sends a message.
5. Teacher sees only conversations assigned to that teacher.
6. Teacher replies.
7. Parent receives the reply notification.
8. A second school cannot access either the conversation or notifications.
