# Parent Portal — Phase 1

Implemented a dedicated parent authentication and read-only portal without changing the existing staff `users.role` constraint.

## Included
- `parent_accounts` and `parent_students` migrations
- Parent login/logout and session isolation
- Parent dashboard with child switching
- My Children
- Published Results + PDF download
- Attendance history
- Class timetable
- Published report history
- Teacher contact details via email/phone
- Parent notifications
- Parent profile/password settings
- Admin/sub-admin parent-account creation/reset from the existing guardian profile
- Parent notification targeting
- Parent navigation in the shared modern UI

## RBAC / isolation
- Parent sessions use a dedicated `parent_id`; they are not staff `user_id` sessions.
- Every child lookup requires an explicit `parent_students` link and school match.
- Results require published terms and enrollment for the child's session.
- Parent accounts are scoped to one school.
- Staff/admin permissions are unchanged.
