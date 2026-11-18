# V109 — role-based dashboard charts (spec item 10), built from real records only
Everything in V107 / V108 notes still applies. V109 = V108 + the charts below.

## What each role now sees
| Role | Charts (all from the database, scoped to the school) |
|---|---|
| **Super Admin** | Schools by status (Active / Suspended / Inactive), school registration trend (12 months), school growth (cumulative), enrolment across schools (10 largest) |
| **School Admin** (School Analytics) | existing: enrolment, gender panel, class performance, attendance, term trend. **New:** subject performance, pass / fail distribution |
| **Teacher** | existing: class performance, attendance, enrolment, gender. **New:** subject performance, pass / fail distribution (for the teacher's classes; follow the term / class filter) |
| **Registrar** | New admissions per month, transfers and withdrawals per month (from the status history), enrolment by class |
| **Student** | existing: academic trend (term by term), subject scores, attendance |
| **Parent** | existing: academic trend, attendance. **New:** subject scores for the selected child — the same figures the child sees |

## Rules the charts follow
* **Real data only.** `role_charts.py` returns chart specs built from SQL; a chart with nothing to show says so ("No data recorded…") instead of drawing zeros.
  Records that cannot be plotted are counted in the subtitle (e.g. "3 students have no admission date recorded and are not shown").
  Subjects with no score are gaps, never zeros. Pass/fail uses the school's own fail grade (a student with no scores is "not yet assessed").
* **Isolation.** School views are filtered by school (and the teacher's own classes); only the Super Admin sees platform-wide figures, and nothing platform-wide
  reaches a school page. The filter API refuses classes outside the user's scope.
* **Accessible and responsive.** Every chart has an accessible name and a "View as table" text alternative; cards reflow from desktop to phone; integer axes for counts.
* **Light / dark and text size.** Charts redraw when the theme or the A- / A+ size changes. The React term / class filter refreshes the new charts too.

## NOT built (no data exists)
**Accountant charts** (fees collected, outstanding, payment trend, payment-method split, class-based collection). This build has no fee ledger: no fee structures, invoices,
payments or payment methods. The only fee data is one expected / collected figure per school (`school_fee_summary`), which nothing in the application writes. Charting
it would be either empty or invented, so nothing is drawn. This needs a real fees module first (fee structures per class, invoices per student, payments with method and
date) — it is a feature, not a chart. Student attendance charts appear only once attendance has been recorded.

## Tests
`tests/v107_scenarios.py` (166 checks): every chart figure is checked against an independent calculation from the raw tables (admissions per month, transfers vs
withdrawals, enrolment, school status counts, cumulative growth, subject averages, pass/fail totals), plus empty states, tenant isolation and the filter API.
