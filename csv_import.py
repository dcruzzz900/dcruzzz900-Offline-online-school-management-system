"""V104: one careful CSV reader + validators for every import in the app (students, class register, scores).

Rules:
* headings are matched to the database field names exactly (case/spacing/hyphens are forgiven: 'Admission No' -> admission_no);
* a clear message names missing headings, ignored extra columns, and every bad cell as 'Row N, column X: what is wrong';
* NOTHING is saved unless every row is valid (callers validate first, then write in one transaction), so a wrong file can never
  half-import or overwrite good records;
* blank cells never erase existing data (callers only change what the file actually provides).
"""
import csv
import datetime
import io
import re

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000

ALIASES = {
    "admission_number": "admission_no", "admission_no.": "admission_no", "admission": "admission_no",
    "register_number": "admission_no", "register_no": "admission_no", "reg_no": "admission_no",
    "firstname": "first_name", "first": "first_name", "lastname": "last_name", "surname": "last_name", "last": "last_name",
    "othernames": "other_names", "other_name": "other_names", "middle_name": "other_names",
    "class": "class_name", "classname": "class_name", "class_arm": "class_name",
    "dob": "date_of_birth", "birth_date": "date_of_birth", "date_of_birth.": "date_of_birth",
    "ca_1": "ca1", "ca_2": "ca2", "ca_3": "ca3", "exam_score": "exam",
    "guardian_name": "parent_name", "guardian_phone": "parent_phone", "guardian_email": "parent_email",
}


class CsvProblem(Exception):
    """The file as a whole cannot be used (message is shown to the user)."""


def _norm(h):
    h = (h or "").replace("\ufeff", "").strip().lower()
    h = re.sub(r"[\s\-]+", "_", h)
    return ALIASES.get(h, h)


def read_table(file_storage, required, optional=(), min_any=None):
    """-> (rows, ignored_columns). rows = [(row_number, {heading: cleaned string})]. Raises CsvProblem for file-level problems.
    min_any: a set of headings of which at least one must be present (e.g. the score columns)."""
    raw = file_storage.read()
    if not raw or not raw.strip():
        raise CsvProblem("The file is empty.")
    if len(raw) > MAX_BYTES:
        raise CsvProblem("The file is too large (limit 5 MB). Split it into smaller files.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")          # files saved by older Excel
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].strip().lstrip('"').startswith("#")):
        lines.pop(0)                                             # blank lines / '# comment' lines before the headings
    if not lines:
        raise CsvProblem("The file has no heading row.")
    first = lines[0]
    delim = max((",", ";", "\t"), key=lambda d: first.count(d))
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
    try:
        header_raw = next(reader)
    except StopIteration:
        raise CsvProblem("The file has no heading row.")
    headers = [_norm(h) for h in header_raw]
    seen, dups = set(), set()
    for h in headers:
        if h and h in seen:
            dups.add(h)
        seen.add(h)
    if dups:
        raise CsvProblem(f"These headings appear more than once: {', '.join(sorted(dups))}.")
    missing = [c for c in required if c not in headers]
    if missing:
        raise CsvProblem(f"Missing required heading(s): {', '.join(missing)}. Your file has: {', '.join(h for h in headers if h) or '(none)'}. "
                         f"Download the template and keep its headings exactly.")
    if min_any and not (set(min_any) & set(headers)):
        raise CsvProblem(f"The file needs at least one of these headings: {', '.join(sorted(min_any))}.")
    known = set(required) | set(optional)
    ignored = [h for h in headers if h and h not in known]
    rows = []
    for n, cells in enumerate(reader, start=2 + (len(text.splitlines()) - len(lines))):
        if not any((c or "").strip() for c in cells):
            continue
        extra = [c for c in cells[len(headers):] if (c or "").strip()]
        row = {h: (cells[i].strip() if i < len(cells) and cells[i] is not None else "") for i, h in enumerate(headers) if h}
        if extra:
            row["__extra__"] = True
        rows.append((n, row))
        if len(rows) > MAX_ROWS:
            raise CsvProblem(f"Too many rows (limit {MAX_ROWS} per file). Split the file.")
    if not rows:
        raise CsvProblem("The file has headings but no data rows.")
    return rows, ignored


# ---------------------------------------------------------------- cell validators: return (clean_value, error_or_None)
def v_gender(v):
    if not v:
        return None, None
    m = {"m": "M", "male": "M", "f": "F", "female": "F"}.get(v.strip().lower())
    return (m, None) if m else (None, f"gender '{v}' is not valid - use M or F")


def v_date(v):
    if not v:
        return None, None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.datetime.strptime(v.strip(), fmt).date()
            if d > datetime.date.today() or d.year < 1950:
                return None, f"date '{v}' is not a sensible date of birth"
            return d.isoformat(), None
        except ValueError:
            continue
    return None, f"date '{v}' is not valid - use YYYY-MM-DD (for example 2012-05-14)"


def v_email(v):
    if not v:
        return None, None
    return (v.strip(), None) if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v.strip()) else (None, f"email '{v}' is not valid")


def v_phone(v):
    if not v:
        return None, None
    digits = re.sub(r"\D", "", v)
    return (v.strip(), None) if re.fullmatch(r"[+\d][\d\s\-()]{5,20}", v.strip()) and 7 <= len(digits) <= 15 else (None, f"phone number '{v}' is not valid")


def v_number(v):
    """Blank -> (None, None) meaning 'not provided'."""
    if v is None or str(v).strip() == "":
        return None, None
    try:
        return float(str(v).strip().replace(",", ".")), None
    except ValueError:
        return None, f"'{v}' is not a number"


def summarize(errors, limit=12):
    shown = errors[:limit]
    more = f" ... and {len(errors) - limit} more problem(s)" if len(errors) > limit else ""
    return " | ".join(shown) + more
