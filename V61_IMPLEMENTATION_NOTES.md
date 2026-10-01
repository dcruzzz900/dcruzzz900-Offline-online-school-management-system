# V61 — Complete Fixes & Enhancements

This release is an additive online-first upgrade of the V60 school management system.

## Implemented
- Tenant-scoped School Setup and Multi-School Control Centre error handling with server-side technical logging.
- Public Student Signup removed from the welcome/registration UI.
- Student login accepts Username, Admission No. or Register No.
- Student first login requires a secure class login code; later logins do not.
- Form/Class Teacher and authorized admins can generate, rotate and revoke class login codes.
- Student self-service is restricted to username/password account settings; official school data remains staff-managed.
- Dashboard search for tenant-scoped students, staff and classes.
- Expanded score audit history: old/new totals, difference, actor role, reason, result status and tenant.
- Overall Position and Subject Position independent school settings.
- Subject competition ranking with ties handled consistently.
- Result template selection: Classic, Modern, Compact, Detailed.
- Result print CSS isolates the result sheet to A4 print output.
- Automatic next-term creation after publication and next academic-session creation after the final term.
- Passport photo is surfaced as the authenticated user's dashboard avatar and links to profile.
- Timetable day ownership validation and timetable conflict validation repair.
- V61 migration is additive and idempotent.

## Validation
Python syntax checks pass and the targeted RBAC/security/UI regression tests pass.

The full end-to-end V60 test cannot execute in this build environment because Flask is not installed and external package installation is unavailable. The deployment's `requirements.txt` already declares Flask and the other runtime dependencies.
