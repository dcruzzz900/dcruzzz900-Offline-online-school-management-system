# PostgreSQL migration inventory — v113

> Static source inventory only. This is not a PostgreSQL migration script.

- Numbered migrations: **23**
- Named migration steps: **76**
- Total registered entries: **99**
- Entries flagged for manual review: **82**

## SQLite-specific constructs found inside registered migration functions

- `ensure_column`: 155
- `executescript`: 1
- `lastrowid`: 2
- `pragma`: 8
- `rowid`: 10
- `sqlite_catalog`: 1
- `sqlite_date_functions`: 15
- `sqlite_upsert`: 16
- `table_rebuild`: 3
- `trigger_ddl`: 36

## Ordered migration registry

| Registry | Order | Key | Function | Source lines | Review flags |
|---|---:|---|---|---:|---|
| MIGRATIONS | 1 | `version_001` | `migration_001_baseline` | 98–100 | executescript (1) |
| MIGRATIONS | 2 | `version_002` | `migration_002_multi_school` | 103–136 | lastrowid (1), ensure_column (1) |
| MIGRATIONS | 3 | `version_003` | `migration_003_student_fields` | 139–146 | ensure_column (1) |
| MIGRATIONS | 4 | `version_004` | `migration_004_school_email_and_logo_settings` | 151–162 | ensure_column (1) |
| MIGRATIONS | 5 | `version_005` | `migration_005_expand_user_roles` | 165–194 | table_rebuild (1) |
| MIGRATIONS | 6 | `version_006` | `migration_006_merge_admission_register` | 197–242 | table_rebuild (1), ensure_column (1) |
| MIGRATIONS | 7 | `version_007` | `migration_007_terms_publish_flag` | 245–249 | ensure_column (1) |
| MIGRATIONS | 8 | `version_008` | `migration_008_more_skill_traits` | 252–260 | sqlite_upsert (1) |
| MIGRATIONS | 9 | `version_009` | `migration_009_signature_dates` | 263–265 | ensure_column (2) |
| MIGRATIONS | 10 | `version_010` | `migration_010_enrollments` | 268–302 | sqlite_upsert (1) |
| MIGRATIONS | 11 | `version_011` | `migration_011_student_login` | 305–314 | ensure_column (2) |
| MIGRATIONS | 12 | `version_012` | `migration_012_platform_tier` | 317–343 | ensure_column (1) |
| MIGRATIONS | 13 | `version_013` | `migration_013_notifications` | 346–363 | ensure_column (2) |
| MIGRATIONS | 14 | `version_014` | `migration_014_attendance_records` | 366–392 | — |
| MIGRATIONS | 15 | `version_015` | `migration_015_auto_comments` | 395–401 | ensure_column (2) |
| MIGRATIONS | 16 | `version_016` | `migration_016_cumulative_results` | 404–409 | ensure_column (1) |
| MIGRATIONS | 17 | `version_017` | `migration_017_class_category` | 412–418 | ensure_column (1) |
| MIGRATIONS | 18 | `version_018` | `migration_018_learning_materials` | 421–451 | — |
| MIGRATIONS | 19 | `version_019` | `migration_019_staff_attendance` | 454–474 | — |
| MIGRATIONS | 20 | `version_020` | `migration_020_font_customization` | 477–483 | ensure_column (2) |
| MIGRATIONS | 21 | `version_021` | `migration_021_school_subdomain` | 486–494 | ensure_column (1) |
| MIGRATIONS | 22 | `version_022` | `migration_022_result_date_toggle` | 497–503 | sqlite_date_functions (1), ensure_column (1) |
| MIGRATIONS | 23 | `version_023` | `migration_023_school_activation` | 506–533 | ensure_column (5) |
| STEPS | 1 | `ai_layer` | `migration_048_ai_layer` | 1630–1703 | sqlite_upsert (1) |
| STEPS | 2 | `school_theme` | `migration_049_school_theme` | 1730–1741 | ensure_column (1) |
| STEPS | 3 | `offline_sync` | `migration_024_offline_sync` | 536–651 | ensure_column (4) |
| STEPS | 4 | `deferred_actions` | `migration_025_deferred_actions` | 654–682 | — |
| STEPS | 5 | `sync_triggers` | `migration_026_sync_triggers` | 685–747 | trigger_ddl (2), sqlite_date_functions (3) |
| STEPS | 6 | `user_active_status` | `migration_024_user_active_status` | 1115–1121 | ensure_column (1) |
| STEPS | 7 | `offline_sync_tokens` | `migration_025_offline_sync_tokens` | 1124–1136 | — |
| STEPS | 8 | `ca3_conflicts_audit_tombstones` | `migration_027_ca3_conflicts_audit_tombstones` | 824–905 | trigger_ddl (1), sqlite_date_functions (1), ensure_column (7) |
| STEPS | 9 | `skills_syncable` | `migration_028_skills_syncable` | 908–926 | trigger_ddl (1), sqlite_date_functions (1) |
| STEPS | 10 | `class_arms` | `migration_029_class_arms` | 929–936 | ensure_column (2) |
| STEPS | 11 | `materials_syncable` | `migration_030_materials_syncable` | 1146–1160 | trigger_ddl (1), sqlite_date_functions (1) |
| STEPS | 12 | `user_contact_identifiers` | `migration_031_user_contact_identifiers` | 1163–1171 | ensure_column (2) |
| STEPS | 13 | `student_photo_and_relationship` | `migration_032_student_photo_and_relationship` | 1174–1179 | ensure_column (2) |
| STEPS | 14 | `school_branding_extra` | `migration_033_school_branding_extra` | 1182–1189 | ensure_column (3) |
| STEPS | 15 | `result_theme` | `migration_034_result_theme` | 1192–1197 | ensure_column (2) |
| STEPS | 16 | `digital_signatures` | `migration_035_digital_signatures` | 1200–1212 | ensure_column (5) |
| STEPS | 17 | `student_status_contact` | `migration_036_student_status_contact` | 1215–1222 | ensure_column (2) |
| STEPS | 18 | `attendance_source` | `migration_037_attendance_source` | 1225–1234 | ensure_column (4) |
| STEPS | 19 | `timetable` | `migration_038_timetable` | 1237–1295 | trigger_ddl (1), sqlite_date_functions (1) |
| STEPS | 20 | `tenant_identifiers` | `migration_039_tenant_identifiers` | 1298–1336 | ensure_column (3) |
| STEPS | 21 | `role_permissions` | `migration_036_role_permissions` | 951–1039 | lastrowid (1) |
| STEPS | 22 | `scope_indexes` | `migration_037_scope_indexes` | 1044–1048 | sqlite_date_functions (1) |
| STEPS | 23 | `first_login_onboarding` | `migration_038_first_login_onboarding` | 1051–1059 | ensure_column (3) |
| STEPS | 24 | `role_scope_compat` | `migration_role_scope_compat` | 1062–1086 | sqlite_date_functions (1), ensure_column (7) |
| STEPS | 25 | `school_readiness` | `migration_040_school_readiness` | 1339–1348 | ensure_column (4) |
| STEPS | 26 | `school_subscription` | `migration_041_school_subscription` | 1351–1368 | ensure_column (1) |
| STEPS | 27 | `subscription_plans` | `migration_042_subscription_plans` | 1371–1397 | sqlite_upsert (1) |
| STEPS | 28 | `billing_payments` | `migration_043_billing_payments` | 1400–1439 | — |
| STEPS | 29 | `billing_notification_tracking` | `migration_044_billing_notification_tracking` | 1481–1493 | — |
| STEPS | 30 | `billing_email_notifications` | `migration_045_billing_email_notifications` | 1496–1516 | ensure_column (1) |
| STEPS | 31 | `billing_job_runs` | `migration_046_billing_job_runs` | 1520–1532 | — |
| STEPS | 32 | `payment_gateway_webhooks` | `migration_044_payment_gateway_webhooks` | 1442–1478 | — |
| STEPS | 33 | `billing_financial_audit` | `migration_047_billing_financial_audit` | 1536–1626 | trigger_ddl (8) |
| STEPS | 34 | `billing_finalization` | `migration_053_billing_finalization` | 1744–1804 | — |
| STEPS | 35 | `parent_portal` | `migration_050_parent_portal` | 2807–2880 | — |
| STEPS | 36 | `registration_security_v52_finalize` | `migration_051_registration_security_spec` | 1707–1728 | trigger_ddl (5), rowid (10), ensure_column (12) |
| STEPS | 37 | `auth_signup_audit_v52` | `migration_052_auth_signup_audit_spec` | 2747–2802 | ensure_column (2) |
| STEPS | 38 | `school_auth_branding_v52` | `migration_053_school_auth_branding` | 2888–2908 | ensure_column (1) |
| STEPS | 39 | `system_enhancements_v52` | `migration_054_system_enhancements` | 2913–2936 | ensure_column (4) |
| STEPS | 40 | `online_first_stability_v55` | `migration_055_online_stability` | 2941–2952 | ensure_column (2) |
| STEPS | 41 | `automated_timetable_v2` | `migration_056_automated_timetable_v2` | 2958–3071 | sqlite_upsert (5) |
| STEPS | 42 | `staff_profile_documents_v57` | `migration_057_staff_profile_documents` | 3075–3103 | ensure_column (3) |
| STEPS | 43 | `runtime_schema_repair_v58` | `migration_058_runtime_schema_repair` | 3108–3165 | sqlite_upsert (1), ensure_column (5) |
| STEPS | 44 | `profiles_customfields_v60` | `migration_059_profiles_customfields` | 3190–3358 | trigger_ddl (9), ensure_column (2) |
| STEPS | 45 | `v61_login_codes_audit_results` | `migration_060_v61` | 3369–3507 | sqlite_catalog (1), pragma (2), trigger_ddl (4), sqlite_upsert (1), table_rebuild (1), ensure_column (7) |
| STEPS | 46 | `result_display_settings_v62` | `migration_061_v62` | 3648–3706 | trigger_ddl (1), sqlite_date_functions (1), ensure_column (4) |
| STEPS | 47 | `spec_workflow_attendance_status_v63` | `migration_062_v63_spec` | 3762–3856 | trigger_ddl (1), sqlite_upsert (2), sqlite_date_functions (3), ensure_column (5) |
| STEPS | 48 | `staff_titles_v64` | `migration_063_v64_titles` | 3865–3869 | ensure_column (1) |
| STEPS | 49 | `ai_consent_history_v65` | `migration_064_v65_ai_consent` | 3878–3887 | sqlite_date_functions (1), ensure_column (1) |
| STEPS | 50 | `result_settings_single_home_v65` | `migration_065_v65_result_settings` | 3896–3921 | pragma (2), ensure_column (3) |
| STEPS | 51 | `grading_config_audit_v66` | `migration_066_v66_grading_audit` | 3927–3946 | — |
| STEPS | 52 | `next_term_resumes_v67` | `migration_067_v67_next_term_resumes` | 3952–3987 | pragma (4), ensure_column (1) |
| STEPS | 53 | `print_orientation_fit_font_scale_v73` | `migration_068_v73_print_scaling` | 3993–4008 | ensure_column (3) |
| STEPS | 54 | `password_reset_tokens_v82` | `migration_069_v82_password_reset_tokens` | 4014–4031 | — |
| STEPS | 55 | `activity_log_class_scope_v90` | `migration_070_v90_activity_log` | 4037–4045 | ensure_column (1) |
| STEPS | 56 | `paper_size_v91` | `migration_071_v91_paper_size` | 4051–4063 | ensure_column (3) |
| STEPS | 57 | `days_late_toggle_v99` | `migration_072_v99_days_late_toggle` | 4069–4074 | ensure_column (1) |
| STEPS | 58 | `sample_domain_traits_v100` | `migration_073_v100_sample_domain_traits` | 4080–4108 | sqlite_upsert (3) |
| STEPS | 59 | `sample_colours_v100` | `migration_074_v100_sample_colours` | 4114–4125 | — |
| STEPS | 60 | `student_next_term_resumes_v103` | `migration_075_v103_student_next_term_resumes` | 4131–4134 | ensure_column (1) |
| STEPS | 61 | `targeted_notifications_v103` | `migration_076_v103_targeted_notifications` | 4140–4143 | ensure_column (1) |
| STEPS | 62 | `term_activation_v104` | `migration_077_v104_term_activation` | 4149–4155 | ensure_column (1) |
| STEPS | 63 | `published_sheet_snapshot_v104` | `migration_078_v104_published_sheet_snapshot` | 4161–4165 | ensure_column (1) |
| STEPS | 64 | `admission_unique_per_class_v104` | `migration_079_v104_admission_unique_per_class` | 4171–4184 | trigger_ddl (2) |
| STEPS | 65 | `announcements_v104` | `migration_080_v104_announcements` | 4190–4213 | — |
| STEPS | 66 | `custom_school_info_v104` | `migration_081_v104_custom_school_info` | 4219–4223 | ensure_column (2) |
| STEPS | 67 | `result_custom_fields_v104` | `migration_082_v104_result_custom_fields` | 4229–4250 | ensure_column (1) |
| STEPS | 68 | `fee_summary_v105` | `migration_083_v105_fee_summary` | 4256–4266 | — |
| STEPS | 69 | `result_show_dob_v110` | `migration_084_v110_show_dob` | 4272–4274 | ensure_column (1) |
| STEPS | 70 | `term_next_resumes_v111` | `migration_085_v111_term_next_resumes` | 4280–4283 | ensure_column (1) |
| STEPS | 71 | `result_sheet_gender_v106` | `migration_084_v106_show_gender` | 4347–4350 | ensure_column (1) |
| STEPS | 72 | `ui_preferences_v107` | `migration_085_v107_ui_preferences` | 4356–4362 | — |
| STEPS | 73 | `parent_identity_v107` | `migration_086_v107_parent_identity` | 4368–4372 | ensure_column (2) |
| STEPS | 74 | `custom_background_v107` | `migration_087_v107_custom_background` | 4378–4384 | ensure_column (1) |
| STEPS | 75 | `announcement_duration_v107` | `migration_088_v107_announcement_duration` | 4390–4392 | ensure_column (1) |
| STEPS | 76 | `offline_sync_v113` | `migration_089_offline_sync_v113` | 4399–4432 | ensure_column (1) |

## Interpretation

The counts are pattern matches within registered migration function source bodies. They are not a complete SQL parser, do not include every non-migration query in the application, and do not determine whether a construct is semantically portable. Every flagged entry needs a manual port and scenario tests. The original SQLite migration registry remains unchanged.


## Stage 34 — migration 107: `ai_outputs`

Added `postgres_migration_107_ai_outputs.py` after reviewing the effective SQLite schema snapshot and original table definition. The table has 15 columns, no declared foreign keys, two non-unique indexes (`idx_ai_outputs_school_feature` and `idx_ai_outputs_student`), a status CHECK constraint (`draft`, `approved`, `rejected`), and a tenant-stamping trigger. The PostgreSQL migration uses a BIGINT identity primary key, maps integer identifiers to BIGINT, preserves timestamp fields as TEXT, recreates both indexes, and ports tenant stamping as a BEFORE INSERT trigger. The migration validates the expected columns/types/nullability, exact index set, absence of foreign keys, and presence of the tenant trigger. It is registered as migration 107 and remains separate from SQLite startup. Validation is unit-test based; execution against a live PostgreSQL server remains outstanding.
