# V63 — functional-spec integration (built on v62)

## New / changed in this release
| Spec | What was done |
|---|---|
| 28–30 Publication workflow | `result_publication` (one row per school+class+term) with DRAFT → SUBMITTED → UNDER REVIEW → APPROVED → PUBLISHED, RETURNED, and PUBLISHED → REOPENED → SUBMITTED. Submission validates missing scores, ranges, totals and grades. Return and reopen need a reason. Append-only `result_publication_audit` (actor, role, tenant, previous/new status, reason, event date, server timestamp). Page: **Result approval** (`/results/workflow`). |
| 28 Explicit publication RBAC | `result_workflow_permissions` (submit / review / approve / publish / reopen). A title such as Principal grants nothing. School Admin accounts start with explicit, revocable grants. Manage at **Workflow permissions** (`/admin/result-permissions`, School Admin only). |
| 29 Backend publication guard | `before_request` hook in `v63_spec.py` rejects (403) result PDF/print/e-mail, cumulative PDF, broadsheet PDF/print, class bulk PDF/e-mail, `/reports/broadsheet` export, and the student/parent result pages (view too) unless that class+term is PUBLISHED. Staff may still view/preview; the page carries a banner and a print-neutralising stylesheet. Buttons are hidden when unpublished, but the guard is the control. |
| 28 Score lock | Scores are locked while SUBMITTED / UNDER REVIEW / APPROVED / PUBLISHED (`save_score` and the score-entry page). The old "edit a published score with a reason" path is replaced by Reopen. |
| 28 Legacy toggle | The term-wide Publish/Unpublish buttons no longer publish; they redirect to the workflow. `terms.is_published` now means "at least one class is published" (older screens read it); real decisions use `result_publication`. Terms already published before this release migrate to PUBLISHED classes. |
| 9–12 Attendance | The server decides the date (school timezone, default Africa/Lagos). The submitted date must equal today or is refused with the exact future/backdated messages. No date picker, no manual check-in/out times. Statuses present/absent/late/excused. Duplicates are refused; changes go through a correction (reason required). `server_recorded_at` is immutable (DB trigger). `attendance_audit` is append-only. Staff attendance and self check-in follow the same rules. |
| 3–5 Multiple roles | `/admin/staff/<id>/roles` adds/removes roles without replacing the others; permissions combine; effective immediately; audited. "School Admin" is excluded from selectable roles and rejected on the create/assign paths. Scope check rewritten: score entry needs the real subject+class assignment whatever other roles the person holds; class-wide access needs the Form Teacher class. |
| 6 Score audit | Added action (entered / edited / cleared / changed after return), roles held, class arm and server timestamp to `score_audit`; shown in the audit table. |
| 7, 27 Registrar + status | `/registrar` dashboard: admit students (unique admission number per school, generated if blank; register number per class), change status (Active, Suspended, Withdrawn, Transferred, Graduated, Expelled + school-defined) with effective date, destination/previous school and reason; append-only `student_status_history`. Class/Form Teachers manage register numbers for their own class (`/my-class/<id>/register`). |
| 13–14 | Unread notifications are green with a red dot; read ones neutral; red count badge in the sidebar and header. The dashboard clock is anchored to server time in the school timezone, format `Friday, 03/10/2026 — 7:02 PM`. Teacher dashboard lists all roles. |
| 31 | A student with valid credentials signs in without a class code (the code is only for enrolment/linking). |

## Already present in v62 and left unchanged (verified by the existing suites, not re-implemented)
Single rendering engine for preview/PDF/print, result styles, logo/passport/signature handling, display toggles, custom fields, educational domains, broadsheet styling, tenant checks, Super Admin responsive menu.

## Known limits / decisions to confirm
* Printing from the browser's own menu cannot be blocked server-side; the preview page hides itself in print media, and every print/PDF *endpoint* is blocked.
* Excused absence is stored as `absent` in the legacy `status` column (detail kept in `detail_status`), so totals on result sheets count it as an absence.
* Cumulative PDF is gated by the resolved term's publication.
* Existing tests that published by flipping `terms.is_published` now use `tests/wf_helper.py`; the real workflow is tested in `tests/v63_scenarios.py` (107 checks).

## Tests
`python tests/v63_scenarios.py` (107), `v62` (248), `v61` (292), `v60` (213), plus the 45 contract tests — all pass.
