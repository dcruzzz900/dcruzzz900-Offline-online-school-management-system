"""Standalone PostgreSQL migration 155 for result-sheet display settings.

Ports the effective V62+ SQLite result_display_settings table, including later
columns added by subsequent SQLite migrations. The school_id primary key is
preserved; no secondary indexes, foreign keys, or triggers are declared by the
source table definition.
"""
from __future__ import annotations

from postgres_migrations import PostgresMigration

MIGRATION_VERSION = 155
MIGRATION_NAME = "create_result_display_settings"
MIGRATION_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS result_display_settings (
        school_id BIGINT PRIMARY KEY,
        tenant_id TEXT,
        template TEXT NOT NULL DEFAULT 'professional_classic',
        title TEXT,
        footer_text TEXT,
        watermark_text TEXT,
        accent_color TEXT,
        secondary_color TEXT,
        header_layout TEXT NOT NULL DEFAULT 'logo-left',
        signature_layout TEXT NOT NULL DEFAULT 'split',
        show_passport BIGINT NOT NULL DEFAULT 1,
        show_logo BIGINT NOT NULL DEFAULT 1,
        show_overall_position BIGINT NOT NULL DEFAULT 1,
        show_subject_position BIGINT NOT NULL DEFAULT 0,
        show_attendance BIGINT NOT NULL DEFAULT 1,
        show_days_opened BIGINT NOT NULL DEFAULT 1,
        show_days_present BIGINT NOT NULL DEFAULT 1,
        show_days_absent BIGINT NOT NULL DEFAULT 1,
        show_days_late BIGINT NOT NULL DEFAULT 1,
        show_custom_info BIGINT NOT NULL DEFAULT 1,
        show_additional_fields BIGINT NOT NULL DEFAULT 1,
        show_teacher_comment BIGINT NOT NULL DEFAULT 1,
        show_principal_comment BIGINT NOT NULL DEFAULT 1,
        show_teacher_signature BIGINT NOT NULL DEFAULT 1,
        show_teacher_sign_date BIGINT NOT NULL DEFAULT 1,
        show_principal_signature BIGINT NOT NULL DEFAULT 1,
        show_principal_sign_date BIGINT NOT NULL DEFAULT 1,
        show_score BIGINT NOT NULL DEFAULT 1,
        show_grade BIGINT NOT NULL DEFAULT 1,
        show_remarks BIGINT NOT NULL DEFAULT 1,
        show_admission_no BIGINT NOT NULL DEFAULT 1,
        show_class BIGINT NOT NULL DEFAULT 1,
        show_gender BIGINT NOT NULL DEFAULT 1,
        show_dob BIGINT NOT NULL DEFAULT 1,
        show_session BIGINT NOT NULL DEFAULT 1,
        show_term BIGINT NOT NULL DEFAULT 1,
        show_teacher_name BIGINT NOT NULL DEFAULT 1,
        show_principal_name BIGINT NOT NULL DEFAULT 1,
        show_address BIGINT NOT NULL DEFAULT 1,
        show_email BIGINT NOT NULL DEFAULT 1,
        show_phone BIGINT NOT NULL DEFAULT 1,
        show_motto BIGINT NOT NULL DEFAULT 1,
        show_next_term_resumes BIGINT NOT NULL DEFAULT 0,
        show_all_comments BIGINT NOT NULL DEFAULT 1,
        show_grading_key BIGINT NOT NULL DEFAULT 1,
        show_promotion BIGINT NOT NULL DEFAULT 1,
        show_domains BIGINT NOT NULL DEFAULT 1,
        show_watermark BIGINT NOT NULL DEFAULT 0,
        fit_to_page BIGINT NOT NULL DEFAULT 1,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_by TEXT,
        text_align TEXT NOT NULL DEFAULT 'auto',
        page_orientation TEXT NOT NULL DEFAULT 'portrait',
        font_scale TEXT NOT NULL DEFAULT 'normal',
        paper_size TEXT NOT NULL DEFAULT 'A4',
        custom_width_mm DOUBLE PRECISION,
        custom_height_mm DOUBLE PRECISION
    )""",
)
MIGRATION_SOURCE = ";\n\n".join(MIGRATION_STATEMENTS)

_EXPECTED_COLUMNS = {
    "school_id": ("bigint", True),
    "tenant_id": ("text", False),
    "template": ("text", True),
    "title": ("text", False),
    "footer_text": ("text", False),
    "watermark_text": ("text", False),
    "accent_color": ("text", False),
    "secondary_color": ("text", False),
    "header_layout": ("text", True),
    "signature_layout": ("text", True),
    "show_passport": ("bigint", True),
    "show_logo": ("bigint", True),
    "show_overall_position": ("bigint", True),
    "show_subject_position": ("bigint", True),
    "show_attendance": ("bigint", True),
    "show_days_opened": ("bigint", True),
    "show_days_present": ("bigint", True),
    "show_days_absent": ("bigint", True),
    "show_days_late": ("bigint", True),
    "show_custom_info": ("bigint", True),
    "show_additional_fields": ("bigint", True),
    "show_teacher_comment": ("bigint", True),
    "show_principal_comment": ("bigint", True),
    "show_teacher_signature": ("bigint", True),
    "show_teacher_sign_date": ("bigint", True),
    "show_principal_signature": ("bigint", True),
    "show_principal_sign_date": ("bigint", True),
    "show_score": ("bigint", True),
    "show_grade": ("bigint", True),
    "show_remarks": ("bigint", True),
    "show_admission_no": ("bigint", True),
    "show_class": ("bigint", True),
    "show_gender": ("bigint", True),
    "show_dob": ("bigint", True),
    "show_session": ("bigint", True),
    "show_term": ("bigint", True),
    "show_teacher_name": ("bigint", True),
    "show_principal_name": ("bigint", True),
    "show_address": ("bigint", True),
    "show_email": ("bigint", True),
    "show_phone": ("bigint", True),
    "show_motto": ("bigint", True),
    "show_next_term_resumes": ("bigint", True),
    "show_all_comments": ("bigint", True),
    "show_grading_key": ("bigint", True),
    "show_promotion": ("bigint", True),
    "show_domains": ("bigint", True),
    "show_watermark": ("bigint", True),
    "fit_to_page": ("bigint", True),
    "updated_at": ("text", False),
    "updated_by": ("text", False),
    "text_align": ("text", True),
    "page_orientation": ("text", True),
    "font_scale": ("text", True),
    "paper_size": ("text", True),
    "custom_width_mm": ("double precision", False),
    "custom_height_mm": ("double precision", False),
}


def apply_result_display_settings(conn) -> None:
    for statement in MIGRATION_STATEMENTS:
        conn.execute(statement)

    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema=current_schema() AND table_name=? ORDER BY ordinal_position",
        ("result_display_settings",),
    ).fetchall()
    actual = {
        str(row["column_name"]): (str(row["data_type"]).lower(), str(row["is_nullable"]).upper() == "NO")
        for row in rows
    }
    missing = sorted(set(_EXPECTED_COLUMNS) - set(actual))
    wrong = {
        name: {"actual": actual[name], "expected": expected}
        for name, expected in _EXPECTED_COLUMNS.items()
        if name in actual and actual[name] != expected
    }
    if missing or wrong or set(actual) != set(_EXPECTED_COLUMNS):
        raise RuntimeError(f"result_display_settings columns incompatible: missing={missing}, wrong={wrong}")

    indexes = conn.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND tablename=?",
        ("result_display_settings",),
    ).fetchall()
    if {str(row["indexname"]) for row in indexes} != {"result_display_settings_pkey"}:
        raise RuntimeError("result_display_settings has unexpected or missing indexes")

    constraints = conn.execute(
        "SELECT constraint_type FROM information_schema.table_constraints "
        "WHERE table_schema=current_schema() AND table_name=?",
        ("result_display_settings",),
    ).fetchall()
    if any(str(row["constraint_type"]).upper() == "FOREIGN KEY" for row in constraints):
        raise RuntimeError("result_display_settings has unexpected foreign keys")

    triggers = conn.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE trigger_schema=current_schema() AND event_object_table=?",
        ("result_display_settings",),
    ).fetchall()
    if triggers:
        raise RuntimeError("result_display_settings has unexpected triggers")


def migration() -> PostgresMigration:
    return PostgresMigration(
        version=MIGRATION_VERSION,
        name=MIGRATION_NAME,
        apply=apply_result_display_settings,
        source=MIGRATION_SOURCE,
    )
