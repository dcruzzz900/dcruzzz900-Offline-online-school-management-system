# V94 — Academic Performance and Cumulative/Annual Performance are now mutually exclusive

Your request, from the screenshot of a correctly-themed sheet that was still showing both sections:

> "When Cumulative/Annual performance is toggled on, use this interface exactly for result sheet,
> but if it is turn off academic performance should show. Do not show both Cumulative/Annual
> performance and academic performance on one result sheet when Cumulative/Annual performance is
> toggled on."

Done — across every one of the 16 result-sheet designs.

## What changed

Every result sheet already decides whether to show the **Cumulative / Annual Performance** table
with one condition: `cumulative and cumulative.terms` (cumulative results switched on for the
school, and there's actually something to show). That exact same condition now also decides
whether the **Academic Performance** table (the current term's own CA1/CA2/[CA3]/Exam/Total
breakdown) is shown — just inverted:

- **Cumulative ON, with data** → only **Cumulative / Annual Performance** shows.
- **Cumulative OFF**, or **ON but nothing to show yet** → only **Academic Performance** shows
  (today's behavior, completely unchanged).

They can never both appear, and they can never both disappear, because the one new flag
(`show_cumulative` in `templates/_result_sheet.html`) is built from the identical expression
`_cumulative_breakdown.html` has always self-guarded on — so the two sections can't drift out of
sync with each other.

## Scope: exactly the subject-score table, nothing else

What's hidden, specifically, is the per-term subject score table itself — the thing that's
genuinely redundant once Cumulative/Annual Performance is showing the same subjects' scores across
every term. Everything else your screenshot showed sitting *alongside* Cumulative/Annual
Performance is untouched and stays exactly where it is on every design: attendance, domain
ratings, teacher's and principal's comments, signatures, grading/domain keys, and each design's own
secondary summary boxes (a "Performance Summary" chip, a grade-distribution box, a result-analysis
line, and so on). None of that duplicates Cumulative/Annual Performance, so none of it was touched.

This applies to all 16 designs, across two kinds of template:

- The **10 generic designs** (professional_classic, modern_academic, compact_academic,
  minimal_clean, and 6 others) share one markup block in `templates/_result_sheet.html` — its
  `<section class="rs-perf">...Academic Performance...</section>` is now wrapped in the one new
  condition.
- The **6 bespoke "sample" designs**, each with its own hand-built layout in
  `templates/sheets/*.html`, each had their own per-term score table found and wrapped the same
  way: `assessment_dossier.html`, `boxed_grey_card.html`, `clean_midterm_report.html`,
  `green_cumulative_report.html`, `peach_terminal_sheet.html`, `progress_report_card.html`.

Every `{% include "_cumulative_breakdown.html" %}` call (one per design) is left exactly as it
was — unconditional — because that component has always correctly decided on its own whether it
has anything to show.

## Testing

- New suite `tests/v94_scenarios.py` (49 checks, all passing):
  - **Cumulative ON with real multi-term data**: every one of the 10 sampled designs shows
    Cumulative / Annual Performance and nothing of Academic Performance.
  - **Cumulative OFF**: every design shows Academic Performance exactly as it always has, with no
    trace of Cumulative / Annual Performance — proving today's default is unchanged.
  - **Cumulative ON, but a student with no scores anywhere**: the Cumulative table still shows (an
    all-"-" table, exactly what `_cumulative_breakdown.html` has always rendered in that case) and
    Academic Performance correctly stays hidden rather than popping back up — confirming the new
    flag really does track the existing component's own self-guard, not a different rule.
  - Confirms every `_cumulative_breakdown.html` include is still unconditional in the template
    source, i.e. nothing about its own, already-correct self-gating was touched.
- Updated two existing tests whose assertions were tied to the *old* always-both behavior
  (`tests/v65_scenarios.py`, `tests/v68_scenarios.py`) — both fixtures turn `cumulative_enabled`
  on with real term data, so some of their old text was specifically reading figures that live
  inside the table that's now intentionally hidden in that state. Fixed by updating what each test
  expects to see where, following this project's established "fix the stale assumption, don't
  weaken the check" precedent — not by loosening what's actually verified.
- Full regression run: **all 35 test suites (`tests/v60_scenarios.py` through
  `tests/v94_scenarios.py`), 1,855 checks total, 0 failures.**

## Installing on PythonAnywhere

No database changes this round — just 7 template files:

```bash
cd ~/school-result-system
```

Replace these with the versions in this zip, then reload your web app from the **Web** tab:
- `templates/_result_sheet.html`
- `templates/sheets/assessment_dossier.html`
- `templates/sheets/boxed_grey_card.html`
- `templates/sheets/clean_midterm_report.html`
- `templates/sheets/green_cumulative_report.html`
- `templates/sheets/peach_terminal_sheet.html`
- `templates/sheets/progress_report_card.html`

To confirm: open a result for a student who has scores in more than one term, with **Cumulative /
Annual Results** switched on in Result Display Settings — you should see only the Cumulative /
Annual Performance table, on whichever of the 16 designs you have selected. Then switch Cumulative
off and reprint — you should see the regular Academic Performance table again, exactly as before.

## What's next

Nothing queued — this was a focused fix for what you flagged from your live testing. Let me know
if you'd like anything else looked at.
