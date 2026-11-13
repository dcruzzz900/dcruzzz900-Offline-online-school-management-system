# Desktop Source Integration (my-school-hub-desktop)

The desktop admin dashboard design from `my-school-hub-desktop-dashboard-source-combined.zip` is integrated into the Flask app.

## Files added
- `static/css/msh-desktop.css` — styles ported from the desktop source `css/style.css`
- `templates/partials/desktop_admin_dashboard.html` — desktop dashboard markup with **live** Flask variables
- Reference image: `static/img/reference/dashboard-design-reference.png`

## Behaviour
| Viewport | What shows |
|----------|------------|
| ≤768px | Mobile source layout (`msh-mobile-dashboard`) |
| ≥769px | Desktop source layout (`msh-desktop-dashboard`) |

## Backend
- Stats, gender distribution, result progress, activities, announcements come from the authenticated Flask context
- All links use real routes (`admin_students`, `admin_class_subjects`, `result_workflow`, etc.)
- No separate React SPA process; auth, CSRF and roles remain server-side
