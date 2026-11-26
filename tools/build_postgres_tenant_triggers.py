#!/usr/bin/env python3
"""Generate reviewed PostgreSQL BEFORE INSERT tenant-stamping triggers."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

def qi(s: str) -> str:
    if not IDENT.fullmatch(s):
        raise ValueError(f'Unsafe SQL identifier: {s!r}')
    return '"' + s + '"'

# Explicitly reviewed relationship expressions; never infer a tenant relationship
# from a column name alone.
DIRECT = {
 'ai_audit_log':'NEW.school_id', 'ai_outputs':'NEW.school_id', 'classes':'NEW.school_id',
 'deferred_actions':'NEW.school_id', 'device_credentials':'NEW.school_id',
 'grade_scale':'NEW.school_id', 'grading_config':'NEW.school_id', 'materials':'NEW.school_id',
 'notifications':'NEW.school_id', 'parent_accounts':'NEW.school_id',
 'parent_consent_events':'NEW.school_id', 'parent_students':'NEW.school_id',
 'parent_teacher_messages':'NEW.school_id', 'role_assignments':'NEW.school_id',
 'school_ai_settings':'NEW.school_id', 'sessions':'NEW.school_id',
 'staff_attendance':'NEW.school_id', 'student_ai_consent':'NEW.school_id',
 'subjects':'NEW.school_id', 'sync_conflicts':'NEW.school_id', 'sync_log':'NEW.school_id',
 'timetable_entries':'NEW.school_id', 'timetable_periods':'NEW.school_id', 'users':'NEW.school_id',
}
JOIN_EXPR = {
 'enrollments': 'SELECT s.tenant_id INTO v_tenant_id FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = NEW.class_id',
 'score_history': 'SELECT s.tenant_id INTO v_tenant_id FROM students st JOIN classes c ON c.id = st.class_id JOIN schools s ON s.id = c.school_id WHERE st.id = NEW.student_id',
 'scores': 'SELECT s.tenant_id INTO v_tenant_id FROM students st JOIN classes c ON c.id = st.class_id JOIN schools s ON s.id = c.school_id WHERE st.id = NEW.student_id',
}


def generate(inv: dict, snapshot: dict) -> tuple[str,int]:
    selected=[t for t in inv['triggers'] if t['category']=='tenant_scope_propagation']
    if len(selected)!=29: raise ValueError(f'Expected 29 reviewed tenant triggers, found {len(selected)}')
    tables={t['name']:{c['name'] for c in t['columns']} for t in snapshot['tables']}
    by_table={}
    for t in selected:
        by_table.setdefault(t['table'],[]).append(t)
    expected=set(DIRECT)|set(JOIN_EXPR)|{'students'}
    if set(by_table)!=expected:
        raise ValueError(f'Unreviewed tenant trigger tables: {sorted(set(by_table)^expected)}')
    out=['-- Generated PostgreSQL tenant propagation triggers for v113.',
         '-- Review against production schema and tenant model before applying.',
         '-- BEFORE INSERT assigns NEW fields; it does not issue a second UPDATE.', '']
    generated=0
    for table, triggers in sorted(by_table.items()):
        qi(table)
        cols=tables.get(table,set())
        if not {'tenant_id'} <= cols: raise ValueError(f'{table} lacks tenant_id in effective schema')
        names=[x['name'] for x in triggers]
        for n in names: qi(n)
        # Verify the source SQL still matches the reviewed relationship shape.
        for item in triggers:
            compact=re.sub(r'\s+', '', item['source_sql']).lower()
            if table in DIRECT and 'selecttenant_idfromschoolswhereid=new.school_id' not in compact:
                raise ValueError(f'Unexpected source relationship for {item["name"]}')
            if table == 'enrollments' and 'classescjoinschoolssons.id=c.school_idwherec.id=new.class_id' not in compact:
                raise ValueError(f'Unexpected enrollment relationship for {item["name"]}')
            if table in ('scores','score_history') and 'studentsstjoinclassesconc.id=st.class_idjoinschoolssons.id=c.school_idwherest.id=new.student_id' not in compact:
                raise ValueError(f'Unexpected student-score relationship for {item["name"]}')
            if table == 'students' and ('new.class_id' not in compact or 'schools' not in compact):
                raise ValueError(f'Unexpected student relationship for {item["name"]}')
        fn='app_stamp_tenant_'+table
        qi(fn)
        out += [f'CREATE OR REPLACE FUNCTION {qi(fn)}()', 'RETURNS trigger', 'LANGUAGE plpgsql', 'AS $function$', 'DECLARE', '    v_tenant_id text;', 'BEGIN']
        if table=='students':
            if not {'school_id','class_id'} <= cols: raise ValueError('students lacks school_id/class_id')
            out += ["    IF NEW.school_id IS NULL OR NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN",
                    '        SELECT c.school_id, s.tenant_id INTO NEW.school_id, v_tenant_id',
                    '        FROM classes c JOIN schools s ON s.id = c.school_id',
                    '        WHERE c.id = NEW.class_id;',
                    "        IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN NEW.tenant_id := v_tenant_id; END IF;",
                    '    END IF;']
        elif table in DIRECT:
            if 'school_id' not in cols: raise ValueError(f'{table} lacks school_id')
            out += [f'    IF NEW.tenant_id IS NULL OR NEW.tenant_id = \'\' THEN',
                    f'        SELECT tenant_id INTO v_tenant_id FROM schools WHERE id = {DIRECT[table].replace("NEW.school_id", "NEW.school_id")};',
                    '        NEW.tenant_id := v_tenant_id;', '    END IF;']
        elif table in JOIN_EXPR:
            refcol={'enrollments':'class_id','score_history':'student_id','scores':'student_id'}[table]
            if refcol not in cols: raise ValueError(f'{table} lacks {refcol}')
            out += ["    IF NEW.tenant_id IS NULL OR NEW.tenant_id = '' THEN", f'        {JOIN_EXPR[table]};',
                    '        NEW.tenant_id := v_tenant_id;', '    END IF;']
        else: raise ValueError(f'No reviewed mapping for {table}')
        out += ['    RETURN NEW;', 'END;', '$function$;', '']
        # Student has two SQLite triggers; one combined PG trigger avoids ordering ambiguity.
        pgname='trg_'+table+'_tenant_stamp_pg'
        out += [f'DROP TRIGGER IF EXISTS {qi(pgname)} ON {qi(table)};',
                f'CREATE TRIGGER {qi(pgname)} BEFORE INSERT ON {qi(table)}',
                f'    FOR EACH ROW EXECUTE FUNCTION {qi(fn)}();', '']
        generated+=1
    return '\n'.join(out).rstrip()+'\n',generated


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--inventory',default='postgres_trigger_porting_plan.json'); ap.add_argument('--snapshot',default='postgres_effective_schema_snapshot.json'); ap.add_argument('--output',default='postgres_tenant_triggers.sql'); a=ap.parse_args()
    sql,n=generate(json.loads(Path(a.inventory).read_text()),json.loads(Path(a.snapshot).read_text()))
    Path(a.output).write_text(sql); print(f'Generated {n} PostgreSQL tenant triggers (29 SQLite triggers consolidated).')
if __name__=='__main__': main()
