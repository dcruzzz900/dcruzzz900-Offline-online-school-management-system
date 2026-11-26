-- Generated from the reviewed v113 SQLite immutability guards.
-- Review and apply only after validating the target PostgreSQL schema.
CREATE OR REPLACE FUNCTION app_reject_immutable_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '%', TG_ARGV[0] USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS "trg_attendance_audit_no_delete" ON "attendance_audit";
CREATE TRIGGER "trg_attendance_audit_no_delete" BEFORE DELETE ON "attendance_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_attendance_audit_no_update" ON "attendance_audit";
CREATE TRIGGER "trg_attendance_audit_no_update" BEFORE UPDATE ON "attendance_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_attendance_records_server_ts_immutable" ON "attendance_records";
CREATE TRIGGER "trg_attendance_records_server_ts_immutable" BEFORE UPDATE OF "server_recorded_at" ON "attendance_records"
    FOR EACH ROW WHEN (OLD.server_recorded_at IS NOT NULL AND NEW.server_recorded_at IS DISTINCT FROM OLD.server_recorded_at)
    EXECUTE FUNCTION app_reject_immutable_row('The original attendance timestamp cannot be changed');

DROP TRIGGER IF EXISTS "trg_audit_log_no_delete" ON "audit_log";
CREATE TRIGGER "trg_audit_log_no_delete" BEFORE DELETE ON "audit_log"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_audit_log_no_update" ON "audit_log";
CREATE TRIGGER "trg_audit_log_no_update" BEFORE UPDATE ON "audit_log"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_billing_financial_audit_no_delete" ON "billing_financial_audit";
CREATE TRIGGER "trg_billing_financial_audit_no_delete" BEFORE DELETE ON "billing_financial_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Financial audit records are immutable');

DROP TRIGGER IF EXISTS "trg_billing_financial_audit_no_update" ON "billing_financial_audit";
CREATE TRIGGER "trg_billing_financial_audit_no_update" BEFORE UPDATE ON "billing_financial_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Financial audit records are immutable');

DROP TRIGGER IF EXISTS "trg_billing_payment_history_no_delete" ON "billing_payment_history";
CREATE TRIGGER "trg_billing_payment_history_no_delete" BEFORE DELETE ON "billing_payment_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Payment history records are immutable');

DROP TRIGGER IF EXISTS "trg_billing_payment_history_no_update" ON "billing_payment_history";
CREATE TRIGGER "trg_billing_payment_history_no_update" BEFORE UPDATE ON "billing_payment_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Payment history records are immutable');

DROP TRIGGER IF EXISTS "trg_billing_report_downloads_no_delete" ON "billing_report_downloads";
CREATE TRIGGER "trg_billing_report_downloads_no_delete" BEFORE DELETE ON "billing_report_downloads"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Report download records are immutable');

DROP TRIGGER IF EXISTS "trg_billing_report_downloads_no_update" ON "billing_report_downloads";
CREATE TRIGGER "trg_billing_report_downloads_no_update" BEFORE UPDATE ON "billing_report_downloads"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Report download records are immutable');

DROP TRIGGER IF EXISTS "trg_rbac_audit_log_no_delete" ON "rbac_audit_log";
CREATE TRIGGER "trg_rbac_audit_log_no_delete" BEFORE DELETE ON "rbac_audit_log"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_rbac_audit_log_no_update" ON "rbac_audit_log";
CREATE TRIGGER "trg_rbac_audit_log_no_update" BEFORE UPDATE ON "rbac_audit_log"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_result_publication_audit_no_delete" ON "result_publication_audit";
CREATE TRIGGER "trg_result_publication_audit_no_delete" BEFORE DELETE ON "result_publication_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_result_publication_audit_no_update" ON "result_publication_audit";
CREATE TRIGGER "trg_result_publication_audit_no_update" BEFORE UPDATE ON "result_publication_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_role_assignment_audit_no_delete" ON "role_assignment_audit";
CREATE TRIGGER "trg_role_assignment_audit_no_delete" BEFORE DELETE ON "role_assignment_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_role_assignment_audit_no_update" ON "role_assignment_audit";
CREATE TRIGGER "trg_role_assignment_audit_no_update" BEFORE UPDATE ON "role_assignment_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_score_audit_no_delete" ON "score_audit";
CREATE TRIGGER "trg_score_audit_no_delete" BEFORE DELETE ON "score_audit"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_score_audit_no_update" ON "score_audit";
CREATE TRIGGER "trg_score_audit_no_update" BEFORE UPDATE ON "score_audit"
    FOR EACH ROW WHEN (TRUE)
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_security_events_no_delete" ON "security_events";
CREATE TRIGGER "trg_security_events_no_delete" BEFORE DELETE ON "security_events"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_security_events_no_update" ON "security_events";
CREATE TRIGGER "trg_security_events_no_update" BEFORE UPDATE ON "security_events"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('Audit history is append-only');

DROP TRIGGER IF EXISTS "trg_staff_attendance_server_ts_immutable" ON "staff_attendance";
CREATE TRIGGER "trg_staff_attendance_server_ts_immutable" BEFORE UPDATE OF "server_recorded_at" ON "staff_attendance"
    FOR EACH ROW WHEN (OLD.server_recorded_at IS NOT NULL AND NEW.server_recorded_at IS DISTINCT FROM OLD.server_recorded_at)
    EXECUTE FUNCTION app_reject_immutable_row('The original attendance timestamp cannot be changed');

DROP TRIGGER IF EXISTS "trg_staff_name_history_no_delete" ON "staff_name_history";
CREATE TRIGGER "trg_staff_name_history_no_delete" BEFORE DELETE ON "staff_name_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_staff_name_history_no_update" ON "staff_name_history";
CREATE TRIGGER "trg_staff_name_history_no_update" BEFORE UPDATE ON "staff_name_history"
    FOR EACH ROW WHEN (OLD.admin_notified = NEW.admin_notified)
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_student_ai_consent_events_no_delete" ON "student_ai_consent_events";
CREATE TRIGGER "trg_student_ai_consent_events_no_delete" BEFORE DELETE ON "student_ai_consent_events"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_student_ai_consent_events_no_update" ON "student_ai_consent_events";
CREATE TRIGGER "trg_student_ai_consent_events_no_update" BEFORE UPDATE ON "student_ai_consent_events"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_student_status_history_no_delete" ON "student_status_history";
CREATE TRIGGER "trg_student_status_history_no_delete" BEFORE DELETE ON "student_status_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_student_status_history_no_update" ON "student_status_history";
CREATE TRIGGER "trg_student_status_history_no_update" BEFORE UPDATE ON "student_status_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_subscription_history_no_delete" ON "subscription_history";
CREATE TRIGGER "trg_subscription_history_no_delete" BEFORE DELETE ON "subscription_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');

DROP TRIGGER IF EXISTS "trg_subscription_history_no_update" ON "subscription_history";
CREATE TRIGGER "trg_subscription_history_no_update" BEFORE UPDATE ON "subscription_history"
    FOR EACH ROW
    EXECUTE FUNCTION app_reject_immutable_row('History is append-only');
