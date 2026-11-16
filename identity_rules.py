"""V107: the ONE Date of Birth + Gender rule, shared by every registration / profile form and importer (pure Python, no app imports).
The React fields in static/js/react-ui/identity-fields.js apply the same rules in the browser; this module is the authority."""
import datetime

GENDER_CODES = {"m": "M", "male": "M", "f": "F", "female": "F"}
GENDER_LABELS = {"M": "Male", "F": "Female"}


def normalise_gender(value):
    """V107: 'Male'/'male'/'M' -> 'M', 'Female'/'F' -> 'F', anything else (including blank) -> None. Never guesses."""
    return GENDER_CODES.get((value or "").strip().lower())


def parse_dob(raw, min_age=0):
    """V107: one Date of Birth rule for every form. Accepts the date picker's YYYY-MM-DD (and DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY),
    returns (iso_date, error). Rejects blank, unparseable, future, before 1900, and younger than `min_age` years."""
    raw = (raw or "").strip()
    if not raw:
        return None, "Date of Birth is required."
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            d = None
    if d is None:
        return None, "Date of Birth is not a valid date - use the date picker or YYYY-MM-DD."
    today = datetime.date.today()
    if d > today:
        return None, "Date of Birth cannot be in the future."
    if d.year < 1900:
        return None, "Date of Birth is not a sensible date."
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    if age < min_age:
        return None, f"Date of Birth is not realistic - must be at least {min_age} years old."
    return d.isoformat(), None


def identity_errors(form, min_age=0):
    """V107: the Date of Birth + Gender rule shared by every registration / profile form (the React fields check the same things
    in the browser; this is the authority). Returns (dob_iso, gender_code, [messages])."""
    errors = []
    dob, e = parse_dob(form.get("date_of_birth"), min_age)
    if e:
        errors.append(e)
    gender = normalise_gender(form.get("gender"))
    if not gender:
        errors.append("Gender is required. Choose Male or Female.")
    return dob, gender, errors
