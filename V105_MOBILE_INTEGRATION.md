# Mobile Source Integration (my-school-hub-mobile)

The React mobile dashboard design from `my-school-hub-mobile-dashboard-source.zip` is integrated into the Flask app as follows:

## Files added
- `static/css/msh-mobile.css` – styles ported from React `src/styles.css` (+ Bootstrap Icons CDN)
- `templates/partials/mobile_admin_dashboard.html` – mobile dashboard markup using **live** Flask variables (`stats`, `gender_stats`, `term`, `recent_activities`, `announcements`, etc.)
- Mobile drawer menu + header in `templates/base.html`

## Behaviour
- **≤768px**: React-style mobile dashboard is shown; desktop dashboard is hidden; sidebar drawer menu available
- **≥769px**: Desktop dashboard and sidebar shell remain unchanged
- All links point to real Flask routes (students, staff, classes, billing, promote, results, …)
- Figures come from backend context, not demo numbers

## Not a separate SPA
The React Vite app is **not** run as a separate process. Its UI was ported into Jinja so authentication, CSRF, and role checks stay on the Flask backend.
