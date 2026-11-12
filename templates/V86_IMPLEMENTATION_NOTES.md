# V86 — Collapsible Highlights and Instructions, Sitewide

This round was a single, clearly specified requirement: every "highlight," instruction, tip, help
message, guidance paragraph and informational notice anywhere in the app should be hidden by
default and revealed with one click or tap on a consistent **Help (?)** control — on every screen,
for every role (Super Admin, School Admin, Sub-Admin, teachers, students, parents, staff) — while
the handful of things that are never safe to hide (required fields, validation errors, security
and consent warnings, real-time status, actionable feedback) stay exactly as visible as they are
today.

This wasn't a new idea for the app. **V74** already introduced exactly this component — for 8
specific explainer paragraphs — using the browser's own native "disclosure" element rather than
custom JavaScript. V86 is that same component, applied everywhere else it belongs.

## What actually changed

A full read-through of all 165 page templates in the app found **61 further places** where a
paragraph, tip, or notice was pure "how this works" explanation rather than something the page
needs you to see right now. Every one of them now uses the identical pattern V74 established:

```html
<details class="hlp">
  <summary class="hlp-t">How this works</summary>
  <p class="muted hlp-b">...the explanation...</p>
</details>
```

Closed by default. Click or tap the label (with its small "?" marker) and it opens in place, no
page reload, no layout jump elsewhere on the page. Click again to close it. No text was deleted —
every explanation that used to sit in the open on the page is still there, word for word, just one
tap away instead of always on screen.

Across the app, that's now **47 pages** using this component (70 individual collapsible blocks in
total, counting V74's original 8), grouped roughly like this:

- **School Admin settings and setup** — email/SMTP setup, grading scale rules, student CSV import,
  Sub-Admin permission scope, Term management, promotion, the First-Day and Setup Wizard checklists,
  custom field creation, the result-workflow explainer, school branding/subdomain notes, and the
  Settings page (username change, adding contact info, clearing demo data).
- **Day-to-day staff screens** — roll call, the class attendance register, score entry (the CSV
  round-trip explanation), staff profile editing, role/permission explanations, and the class
  roster page.
- **Student- and parent-facing pages** — the student profile ("giving a student their own login"),
  the parent profile explainer, the cumulative result's "how the average is calculated" note (on
  the staff, student, and parent versions of that page alike), login-recovery help, first-login
  help, and activation guidance.
- **AI features** — the bulk AI-consent update explainer, the suggested-workflow notice on AI
  learning materials, and the "how AI works here" explanation on AI result analysis.
- **Super Admin / platform and billing** — backup/restore procedure notes, billing and subscription
  mechanics, plan-change and usage-limit explanations, the Control Center's status glossary, and the
  school-facing billing portal's renewal instructions.

## What was deliberately left alone, and why

The requirement itself draws a clear line, and this is the part that took the most care to get
right — wrapping the wrong things would have hidden information people actually need in the
moment, which is the opposite of the goal. None of the following were touched:

- **Required-field markers, form labels, and validation error messages** — if a field is required
  or something you typed is wrong, you see that immediately, same as always.
- **Security and consent warnings** — for example, the billing portal's "never send your school
  password or payment-gateway secret key as proof of payment" notice, or the account-deletion
  warning on the Settings page, both stay in plain sight exactly where they were.
- **Real-time status and empty-state messages** — "No scores entered yet," "No AI activity
  recorded," a term's actual Published/Draft status, today's date on the attendance register — these
  report what's true right now, not how something works in general, so they're never hidden.
- **Short signposts** — a one-line "see X for that" pointer to another page isn't the kind of
  clutter this requirement is about, so those were left as plain text too.

Two pages needed a closer look rather than a simple yes/no: the **roll call** and **class
attendance** screens both open with a sentence that mixes a live fact ("recorded for today only —
{{ the actual current date and time }}") with a general explanation ("the date comes from the
school's server, not your device's clock"). Hiding the whole sentence would have hidden the live
date, which the requirement explicitly protects. So on those two pages only, the sentence was split:
the live date/time stays visible as plain text exactly as before, and only the general
mechanism explanation moved behind the Help control next to it.

## Accessibility

The requirement describes the usual way this is built: a button with `aria-expanded` and
`aria-controls` attributes wired up by hand. This implementation reaches the same result a
different way — the same way V74 already did it — by using the browser's own native `<details>`
and `<summary>` elements instead of a custom button-plus-div pair.

The reason: `<details>`/`<summary>` already **is** an accessible disclosure control, built into
every modern browser. It's reachable by Tab, opens and closes with Enter or Space without any
JavaScript, and screen readers announce "collapsed" or "expanded" directly from the element's own
`open` attribute — which is exactly what hand-written `aria-expanded`/`aria-controls` attributes
are for in the first place. Adding both would mean keeping two sources of truth about the same
state in sync by hand, which is a good way to introduce the very bug (a screen reader announcing
the wrong state) that those attributes exist to prevent. Using the browser's native version gets
the same outcome — reliably, with less code, and with one fewer thing that can quietly drift out of
sync later.

A small focus-visible outline was also added in `static/css/style.css` so the Help control is
clearly visible when reached by keyboard, matching the school's own accent color.

## What this did not touch

- No database changes. No migration. This is a template- and stylesheet-only change.
- No existing records, permissions, saved settings, or sync behavior were touched.
- No form was changed, renamed, or had its fields reordered — the collapsible wrapper sits
  around explanatory text only, never around a field or a button.
- The 8 explainer blocks V74 already converted were left as they were; V86 only added further
  ones using the identical pattern, so there is nothing to "re-do."

## Testing

- `tests/v86_scenarios.py` (+ `tests/test_v86_behavior.py` pytest wrapper) — new, 41 checks,
  spanning School Admin, staff, student, parent, and Super Admin/platform logins. It confirms: a
  representative sample of the new Help blocks are present, closed by default, and their text is
  still there (collapsed, not deleted); the roll-call page's live "today" date/time stays visible
  as plain text outside any Help control while only the general explanation moved behind one; a
  failed login still shows its error immediately; the account-deletion warning on the Settings page
  stays in plain sight; a term's real Published/Draft status is plain table data, not hidden; and
  the Help control itself is a real `<summary>` inside a real `<details>` element, confirming the
  native keyboard/screen-reader behavior described above is actually in the markup.
- Full regression suite (`tests/v60_scenarios.py` through `tests/v86_scenarios.py`): **1,648
  checks, 0 failed** (the prior 1,607 from V85, plus this round's 41).
- Sanity-checked the whole app still imports and serves all 315 routes with no errors after the
  ~47 template edits.

## Installing this update on PythonAnywhere

1. Open a Bash console on PythonAnywhere.
2. Back up your database first, as always:
   ```bash
   cp /home/<youraccount>/school/instance/*.db /home/<youraccount>/school_backup_before_v86.db
   ```
3. Upload the new zip and replace these files:
   - `static/css/style.css` (the Help control's styling, extended with a focus outline)
   - `tests/v86_scenarios.py` (new), `tests/test_v86_behavior.py` (new)
   - Every template below — each one just wraps existing explanatory text in a collapsible Help
     control; nothing else on these pages changed:
     - `templates/account_recovery.html`
     - `templates/activate.html`
     - `templates/admin_custom_field_form.html`
     - `templates/admin_email.html`
     - `templates/admin_first_login.html`
     - `templates/admin_grading.html`
     - `templates/admin_promote.html`
     - `templates/admin_school.html`
     - `templates/admin_school_info.html`
     - `templates/admin_setup_wizard.html`
     - `templates/admin_students.html`
     - `templates/admin_subadmins.html`
     - `templates/admin_terms.html`
     - `templates/ai_consent.html`
     - `templates/ai_learning_materials.html`
     - `templates/ai_result_analysis.html`
     - `templates/cumulative_broadsheet.html`
     - `templates/cumulative_result.html`
     - `templates/login.html`
     - `templates/materials.html`
     - `templates/my_class_roster.html`
     - `templates/parent_cumulative_result.html`
     - `templates/parent_profile.html`
     - `templates/platform_backups.html`
     - `templates/platform_billing.html`
     - `templates/platform_billing_audit.html`
     - `templates/platform_billing_reports.html`
     - `templates/platform_control_center.html`
     - `templates/platform_new_school.html`
     - `templates/platform_plans.html`
     - `templates/platform_school_billing.html`
     - `templates/platform_school_subscription.html`
     - `templates/platform_subscriptions.html`
     - `templates/result_display_settings.html`
     - `templates/result_preview.html`
     - `templates/result_workflow.html`
     - `templates/roll_call.html`
     - `templates/school_billing_portal.html`
     - `templates/score_entry.html`
     - `templates/settings_hub.html`
     - `templates/staff_attendance.html`
     - `templates/staff_profile.html`
     - `templates/staff_roles.html`
     - `templates/student_account.html`
     - `templates/student_cumulative_result.html`
     - `templates/student_login.html`
     - `templates/student_profile.html`
     - `templates/theme_branding.html`
     - `templates/timetable_edit_v2.html`
     - `templates/timetable_setup_v2.html`
4. Go to the **Web** tab and click **Reload**.
5. Nothing needs reconfiguring or re-entering — this is a pure display change. To see it, open any
   page that used to show a longer explanatory paragraph (for example **Admin → Grading**, or the
   **Setup Wizard**) and you'll see a small "**? How this works**"-style label where the paragraph
   used to sit; click it to expand.

## Where this leaves things

The "Collapsible Highlights and Instructions" requirement is complete, sitewide, using the same
lightweight component V74 introduced rather than a second, parallel mechanism. Nothing further is
currently queued.
