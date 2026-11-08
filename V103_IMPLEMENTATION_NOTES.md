# V103
1. Subject position: the Pos. columns on the Cumulative/Annual table (each term AND overall) now follow "Show subject position" (HTML, print and fallback PDF; column widths re-balance).
2. Start review: opens that class's submitted results (/class/<id>/results?term_id=..&review=1) with a banner: status + who submitted + when, and a link back to Result Workflow.
3. Approve: notifies the class/form teacher (and whoever submitted) - "Results approved ... approved by <name> (<role>)". New notifications.target_user_id (migration 076); other users never see it.
4. Cumulative Broadsheet: per subject, every term's CA1, CA2, (CA3), Exam, Total + cumulative average/grade; overall average and position. Prints landscape.
5. Signature: blank space above the line 10mm -> 6.5mm; an uploaded signature now sits ON a full-width line (the line no longer shrinks to the image).
6. Next Term Resumes: field on the Academic Record page (per result; prefilled with the school's next-term date; blank = school date). Shown on the sheet/PDF only when "Show Next Term Resumes" is on. student_term_info.next_term_resumes (migration 075).
7. The Academic Record card shows the real status (Draft / Submitted / Under review / Approved / Published), "Published" only when published.
8. Download = print: audited all 35 display switches one by one (cumulative + per-term, two designs): print and PDF now hide/show identical content. Fixed: promotion box followed the wrong switch in the PDF; label "Admission / Register No.".
9. The "printing in a plain, generic layout / PDF engine" warning banner was removed.
10. Accent colour now lives in Result Display Settings (renamed "Accent colour", live preview updates the sheet + all design thumbnails as you change it). Removed from Theme & Branding together with its mini result preview.
Tests: tests/v103_scenarios.py (38 checks); all suites v60-v102 pass (v67/v80/v87 assertions updated for the changed markup/banner).
