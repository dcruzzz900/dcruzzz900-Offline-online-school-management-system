-- Generated PostgreSQL tenant propagation triggers for v113.
-- Review against production schema and tenant model before applying.
-- BEFORE INSERT assigns NEW fields; it does not issue a second UPDATE.

CREATE OR REPLACE FUNCTION "app_stamp_tenant_ai_audit_log"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_ai_audit_log_tenant_stamp_pg" ON "ai_audit_log";
CREATE TRIGGER "trg_ai_audit_log_tenant_stamp_pg" BEFORE INSERT ON "ai_audit_log"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_ai_audit_log"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_ai_outputs"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_ai_outputs_tenant_stamp_pg" ON "ai_outputs";
CREATE TRIGGER "trg_ai_outputs_tenant_stamp_pg" BEFORE INSERT ON "ai_outputs"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_ai_outputs"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_classes"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_classes_tenant_stamp_pg" ON "classes";
CREATE TRIGGER "trg_classes_tenant_stamp_pg" BEFORE INSERT ON "classes"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_classes"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_deferred_actions"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_deferred_actions_tenant_stamp_pg" ON "deferred_actions";
CREATE TRIGGER "trg_deferred_actions_tenant_stamp_pg" BEFORE INSERT ON "deferred_actions"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_deferred_actions"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_device_credentials"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_device_credentials_tenant_stamp_pg" ON "device_credentials";
CREATE TRIGGER "trg_device_credentials_tenant_stamp_pg" BEFORE INSERT ON "device_credentials"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_device_credentials"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_enrollments"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT s.tenant_id INTO v_tenant_id FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = NEW.class_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_enrollments_tenant_stamp_pg" ON "enrollments";
CREATE TRIGGER "trg_enrollments_tenant_stamp_pg" BEFORE INSERT ON "enrollments"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_enrollments"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_grade_scale"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_grade_scale_tenant_stamp_pg" ON "grade_scale";
CREATE TRIGGER "trg_grade_scale_tenant_stamp_pg" BEFORE INSERT ON "grade_scale"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_grade_scale"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_grading_config"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_grading_config_tenant_stamp_pg" ON "grading_config";
CREATE TRIGGER "trg_grading_config_tenant_stamp_pg" BEFORE INSERT ON "grading_config"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_grading_config"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_materials"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_materials_tenant_stamp_pg" ON "materials";
CREATE TRIGGER "trg_materials_tenant_stamp_pg" BEFORE INSERT ON "materials"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_materials"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_notifications"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_notifications_tenant_stamp_pg" ON "notifications";
CREATE TRIGGER "trg_notifications_tenant_stamp_pg" BEFORE INSERT ON "notifications"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_notifications"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_parent_accounts"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_parent_accounts_tenant_stamp_pg" ON "parent_accounts";
CREATE TRIGGER "trg_parent_accounts_tenant_stamp_pg" BEFORE INSERT ON "parent_accounts"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_parent_accounts"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_parent_consent_events"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_parent_consent_events_tenant_stamp_pg" ON "parent_consent_events";
CREATE TRIGGER "trg_parent_consent_events_tenant_stamp_pg" BEFORE INSERT ON "parent_consent_events"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_parent_consent_events"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_parent_students"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_parent_students_tenant_stamp_pg" ON "parent_students";
CREATE TRIGGER "trg_parent_students_tenant_stamp_pg" BEFORE INSERT ON "parent_students"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_parent_students"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_parent_teacher_messages"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_parent_teacher_messages_tenant_stamp_pg" ON "parent_teacher_messages";
CREATE TRIGGER "trg_parent_teacher_messages_tenant_stamp_pg" BEFORE INSERT ON "parent_teacher_messages"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_parent_teacher_messages"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_role_assignments"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_role_assignments_tenant_stamp_pg" ON "role_assignments";
CREATE TRIGGER "trg_role_assignments_tenant_stamp_pg" BEFORE INSERT ON "role_assignments"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_role_assignments"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_school_ai_settings"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_school_ai_settings_tenant_stamp_pg" ON "school_ai_settings";
CREATE TRIGGER "trg_school_ai_settings_tenant_stamp_pg" BEFORE INSERT ON "school_ai_settings"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_school_ai_settings"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_score_history"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT s.tenant_id INTO v_tenant_id FROM students st JOIN classes c ON c.id = st.class_id JOIN schools s ON s.id = c.school_id WHERE st.id = NEW.student_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_score_history_tenant_stamp_pg" ON "score_history";
CREATE TRIGGER "trg_score_history_tenant_stamp_pg" BEFORE INSERT ON "score_history"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_score_history"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_scores"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT s.tenant_id INTO v_tenant_id FROM students st JOIN classes c ON c.id = st.class_id JOIN schools s ON s.id = c.school_id WHERE st.id = NEW.student_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_scores_tenant_stamp_pg" ON "scores";
CREATE TRIGGER "trg_scores_tenant_stamp_pg" BEFORE INSERT ON "scores"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_scores"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_sessions"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_sessions_tenant_stamp_pg" ON "sessions";
CREATE TRIGGER "trg_sessions_tenant_stamp_pg" BEFORE INSERT ON "sessions"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_sessions"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_staff_attendance"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_staff_attendance_tenant_stamp_pg" ON "staff_attendance";
CREATE TRIGGER "trg_staff_attendance_tenant_stamp_pg" BEFORE INSERT ON "staff_attendance"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_staff_attendance"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_student_ai_consent"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_student_ai_consent_tenant_stamp_pg" ON "student_ai_consent";
CREATE TRIGGER "trg_student_ai_consent_tenant_stamp_pg" BEFORE INSERT ON "student_ai_consent"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_student_ai_consent"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_students"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.school_id IS NULL OR NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT c.school_id, s.tenant_id INTO NEW.school_id, v_tenant_id
        FROM classes c JOIN schools s ON s.id = c.school_id
        WHERE c.id = NEW.class_id;
        IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN NEW.tenant_id := v_tenant_id; END IF;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_students_tenant_stamp_pg" ON "students";
CREATE TRIGGER "trg_students_tenant_stamp_pg" BEFORE INSERT ON "students"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_students"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_subjects"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_subjects_tenant_stamp_pg" ON "subjects";
CREATE TRIGGER "trg_subjects_tenant_stamp_pg" BEFORE INSERT ON "subjects"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_subjects"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_sync_conflicts"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_sync_conflicts_tenant_stamp_pg" ON "sync_conflicts";
CREATE TRIGGER "trg_sync_conflicts_tenant_stamp_pg" BEFORE INSERT ON "sync_conflicts"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_sync_conflicts"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_sync_log"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_sync_log_tenant_stamp_pg" ON "sync_log";
CREATE TRIGGER "trg_sync_log_tenant_stamp_pg" BEFORE INSERT ON "sync_log"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_sync_log"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_timetable_entries"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_timetable_entries_tenant_stamp_pg" ON "timetable_entries";
CREATE TRIGGER "trg_timetable_entries_tenant_stamp_pg" BEFORE INSERT ON "timetable_entries"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_timetable_entries"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_timetable_periods"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_timetable_periods_tenant_stamp_pg" ON "timetable_periods";
CREATE TRIGGER "trg_timetable_periods_tenant_stamp_pg" BEFORE INSERT ON "timetable_periods"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_timetable_periods"();

CREATE OR REPLACE FUNCTION "app_stamp_tenant_users"()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    v_tenant_id text;
BEGIN
    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN
        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = NEW.school_id;
        NEW.tenant_id := v_tenant_id;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS "trg_users_tenant_stamp_pg" ON "users";
CREATE TRIGGER "trg_users_tenant_stamp_pg" BEFORE INSERT ON "users"
    FOR EACH ROW EXECUTE FUNCTION "app_stamp_tenant_users"();
