# V105 - School Administration dashboard redesign (laptop, tablet, phone)

* New admin dashboard (templates/admin_dashboard.html, static/css/admin-dashboard.css, partials/ad_icons.html): welcome banner + live school clock; cards for Students and Staff (with male/female counts and %), Classes, Subjects, Parents, School Fees (no link, as requested); Gender Distribution donut; Result Compilation ring + progress bar; Enrollment Trend line chart (pure SVG, no CDN); Quick Access tiles; Recent Activities; Announcements (+ tip).
* Removed from the admin dashboard: Academic workspace, School operations, Quick Actions. The analytics that used to be there moved to /admin/analytics (menu: Reports & Insights -> School Analytics) so nothing was lost.
* Quick Actions -> Quick Access (same role-aware tiles, new look) on teacher / student / parent dashboards.
* Shell: sidebar (brand, status chip), top bar (school name + address, bell badge, role chip).
* Phone (<=700px): purple header with school logo, banner, clock bar, card grid, Gender + Result panels side by side, Quick Access in the design's order (CBT is a non-clickable placeholder), View All toggle, Recent Activities + Announcements, bottom tab bar (Home / Reports / Notifications / More). Tablet (701-1280px): 3-column cards, 2-column panels.
* Data (admin_dashboard_overview): all reads scoped to the school. School Fees reads school_fee_summary (new table, no screen yet -> shows 0 until filled). Result compilation = students who have a score for EVERY subject assigned to their class this term. Staff gender comes from the staff profile gender field.
* Tests: tests/v105_scenarios.py (29 checks); updated v62, v64, v65, v88, v89, v90, v93, v95, v96 and test_rbac_system_fixes for the new layout. All suites v60-v105 and the 45 contract tests pass.

## Known gaps
* Banner photo is cropped from the supplied mockup (low resolution): replace static/img/dashboard-banner.jpg with a proper school photo.
* Footer "Help | Support | Privacy Policy" are not included: those pages do not exist yet.
* Phone cards are 2 per row below 480px (3 per row from 480px): 3 per row is too tight at 390px.
* The sidebar keeps the application's real menu (grouped by category), not the shorter list drawn in the mockup.
