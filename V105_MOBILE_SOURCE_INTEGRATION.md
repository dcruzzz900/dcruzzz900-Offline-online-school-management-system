# Admin dashboard implementation notes

The dashboard JSX is in `src/App.jsx`; its visual system is in the dashboard section at the end of `src/styles.css`. The supplied screenshot is stored separately in `assets/reference/` and is not used as a flattened page background: the interface is built from editable React components and CSS.

## Replace demonstration data before production

The current dashboard uses sample values matching the reference layout (1,024 students, 48 staff, 42 classes, 18 subjects, 982 parents, ₦2,650,000 billed, ₦1,890,000 collected, and 795/1,024 compiled results). Replace these with API response values. Gender counts and activity/announcement content must also come from the logged-in school's authorized data scope.

## Recommended summary response

```json
{
  "students": 1024,
  "staff": 48,
  "classes": 42,
  "subjects": 18,
  "parents": 982,
  "fees": { "billed": 2650000, "collected": 1890000, "currency": "NGN" },
  "gender": { "male": 532, "female": 492 },
  "results": { "compiled": 795, "total": 1024 },
  "recentActivities": [],
  "announcements": []
}
```

This is a proposed response shape, not an existing backend contract. Adapt it to the Flask API and existing database models. Apply tenant scoping and role authorization server-side; do not rely on frontend filtering for security.
