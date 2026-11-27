import unittest
from unittest import mock

from tools import reconcile_postgres_table_details as gap
from tools.reconcile_postgres_table_details import build


class Stage80TableGapReportTests(unittest.TestCase):
    def test_source_table_coverage_totals(self):
        report = build()
        self.assertEqual(report["source_table_count"], 113)
        self.assertEqual(report["postgres_explicit_create_table_coverage"], 112)
        self.assertEqual(report["deliberately_excluded_table_count"], 1)
        self.assertEqual(report["unresolved_table_candidate_count"], 0)
        self.assertEqual(report["unresolved_column_count"], 0)
        self.assertEqual(report["unresolved_foreign_key_declaration_count"], 0)
        self.assertEqual(report["unresolved_index_count"], 0)

    def test_every_source_table_is_ported_or_excluded(self):
        report = build()
        self.assertEqual(
            report["postgres_explicit_create_table_coverage"]
            + report["deliberately_excluded_table_count"]
            + report["unresolved_table_candidate_count"],
            report["source_table_count"],
        )

    def test_non_ddl_references_do_not_claim_table_creation(self):
        report = build()
        self.assertTrue(all(row["classification"] == "NO_EXPLICIT_POSTGRES_CREATE_TABLE_FOUND" for row in report["rows"]))
        unresolved = {row["table"] for row in report["rows"]}
        for ported in ("school_days_v2", "schedule_templates", "schedule_slots", "teacher_availability_v2", "timetable_rooms_v2", "timetable_types_v2", "timetable_configurations_v2", "timetable_versions_v2", "timetable_approvals_v2", "timetable_conflicts_v2", "timetable_audit_v2", "subject_room_requirements_v2", "teacher_workload_profiles_v2", "teacher_timetable_preferences_v2", "timetable_entries_v2", "staff_documents", "timetable_periods", "timetable_entries", "sync_tombstones", "sync_log", "sync_changes", "sync_conflicts"):
            self.assertNotIn(ported, unresolved)
        self.assertNotIn("ui_preferences", unresolved)

    def test_schema_steps_is_deliberately_excluded_with_a_reason(self):
        report = build()
        excluded = {row["table"]: row for row in report["deliberately_excluded_tables"]}
        self.assertEqual(set(excluded), {"schema_steps"})
        self.assertNotIn("schema_steps", {row["table"] for row in report["rows"]})
        self.assertIn("app_schema_migrations", excluded["schema_steps"]["reason"])
        self.assertEqual((excluded["schema_steps"]["column_count"], excluded["schema_steps"]["index_count"]), (2, 1))

    def test_stale_exclusion_of_unknown_table_fails_closed(self):
        with mock.patch.dict(gap.EXCLUDED_TABLES, {"no_such_table": "stale"}):
            with self.assertRaisesRegex(ValueError, "not in the effective schema"):
                build()

    def test_excluding_a_table_that_has_a_postgres_create_fails_closed(self):
        with mock.patch.dict(gap.EXCLUDED_TABLES, {"sync_conflicts": "wrongly excluded"}):
            with self.assertRaisesRegex(ValueError, "explicit PostgreSQL CREATE TABLE"):
                build()

    def test_rendered_report_states_completion_without_overclaiming(self):
        text = gap.render(build())
        self.assertIn("Tables deliberately excluded", text)
        self.assertIn("`schema_steps`", text)
        self.assertIn("still not a live-catalog result", text)

    def test_live_catalog_is_not_claimed(self):
        self.assertFalse(build()["live_postgres_catalog_checked"])


if __name__ == "__main__":
    unittest.main()
