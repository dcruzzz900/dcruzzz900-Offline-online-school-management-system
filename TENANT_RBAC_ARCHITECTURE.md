# Multi-School Tenant ID & Role/Permission Architecture

## Tenant identity
Every school has:
- `school_code`: permanent human-readable School ID (for example `GSSGONINGORA`)
- `tenant_id`: permanent opaque tenant identifier (for example `TEN-8F4K2P9Q`)
- `school_level`: nursery, primary, secondary, or combined

Tenant IDs are identifiers, not passwords or secrets. They are generated server-side and are never accepted as an authorization credential.

## Authentication boundary
`Login -> authenticate user -> load assigned school -> verify active status -> resolve tenant -> grant role/scope permissions`.

The authenticated user's database relationship to the school is authoritative. A tenant ID in a URL, form, JSON body, or browser storage cannot switch a user to another tenant.

## Data isolation
School-owned records have `tenant_id`. Existing `school_id` relationships are retained for compatibility. SQLite triggers re-derive `tenant_id` from the authoritative school relationship on insert/update, preventing a client from assigning a record to another tenant.

## Offline
Offline device credentials are issued only after an authenticated online login. The server re-checks user, school, status, role and tenant on every sync request. Offline records carry the authenticated tenant ID locally. The server remains authoritative during synchronization.

## Nursery / Primary / Secondary
The same role model is used across all school levels:
`User + Role + School + School Level + Scope + Permission + Approval + Status`.

Scopes can include department, class, class arm, subject and term/session.

## Role assignments
`role_assignments` supports primary/secondary roles, scoped permissions, approval, effective dates and expiry. `role_assignment_audit` preserves role-change history. Legacy `users.role` and `users.position` remain for compatibility while the new model is introduced.

## Core security rules
1. No self-escalation.
2. No self-approval.
3. School users cannot grant access to another school.
4. Super Admin is platform-level and cannot be replaced by a school account.
5. Historical records and audit records remain after staff deactivation.
6. Temporary/emergency access has explicit expiry.
