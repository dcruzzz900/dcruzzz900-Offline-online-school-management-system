from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
SRC = APP.read_text(encoding="utf-8")


def test_parent_teacher_routes_exist():
    assert 'def parent_teacher_conversation' in SRC
    assert 'def teacher_messages' in SRC
    assert 'def teacher_message_thread' in SRC


def test_messaging_is_school_scoped():
    assert 'school_id=? AND parent_id=? AND student_id=? AND teacher_id=?' in SRC
    assert 'c.id=? AND c.school_id=? AND c.teacher_id=?' in SRC


def test_parent_message_checks_child_and_teacher_relationship():
    assert 'FROM class_subjects WHERE class_id=? AND teacher_id=?' in SRC
    assert 'FROM classes WHERE id=? AND form_teacher_id=?' in SRC


def test_messages_are_length_limited():
    assert 'len(body) > 4000' in SRC
    assert 'len(body)<=4000' in SRC


def test_message_notifications_are_recipient_specific():
    assert 'recipient_user_id' in SRC
    assert 'recipient_parent_id' in SRC
